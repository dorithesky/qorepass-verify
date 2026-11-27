import { ConnectButton } from "@rainbow-me/rainbowkit";
import { qorechainTestnet } from "@qorechain/evm";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { formatEther, isHex, keccak256, size, toHex } from "viem";
import { useAccount, useBalance, useBlockNumber, useReadContract, useSignMessage } from "wagmi";

/**
 * QorePass verifier — checks a pass on chain.
 *
 * A pass is not a ticket file: it is a record in QorePassRegistry that only the
 * holder's ML-DSA-87 key can check in. This dApp reads that record and says, in
 * one word, what the chain says about it — the venue's side of the flow.
 *
 * What the dApp can and cannot do, stated plainly:
 *  - It reads everything from the chain (passInfo, passState, issuerInfo).
 *  - The QoreX wallet connection is used to read *your* account: your balance,
 *    your EVM authorisation window and, if you are an issuer, your registration.
 *  - It cannot check a pass in for you: check-in needs the holder's ML-DSA-87
 *    signature over `checkInMessage(passId, holderKeyHash)`, which is produced by
 *    the wallet's post-quantum layer and verified by the chain's pqcVerify
 *    precompile. An EVM wallet signature is the classical layer only, so the
 *    dApp never pretends otherwise.
 */

const REGISTRY = "0x312845b8256cafe2ecc8be7addf54f83a836a88b" as const;

const ABI = [
  {
    name: "passInfo",
    type: "function",
    stateMutability: "view",
    inputs: [{ name: "passId", type: "bytes32" }],
    outputs: [
      { name: "issuer", type: "address" },
      { name: "holder", type: "address" },
      { name: "eventId", type: "bytes32" },
      { name: "metaHash", type: "bytes32" },
      { name: "holderKeyHash", type: "bytes32" },
      { name: "validUntil", type: "uint64" },
      { name: "issuedAt", type: "uint64" },
      { name: "checkedInAt", type: "uint64" },
      { name: "status", type: "uint8" },
    ],
  },
  {
    name: "passState",
    type: "function",
    stateMutability: "view",
    inputs: [{ name: "passId", type: "bytes32" }],
    outputs: [{ name: "", type: "uint8" }],
  },
  {
    name: "isValid",
    type: "function",
    stateMutability: "view",
    inputs: [{ name: "passId", type: "bytes32" }],
    outputs: [{ name: "", type: "bool" }],
  },
  {
    name: "issuerInfo",
    type: "function",
    stateMutability: "view",
    inputs: [{ name: "issuer", type: "address" }],
    outputs: [
      { name: "pubkeyHash", type: "bytes32" },
      { name: "nameHash", type: "bytes32" },
      { name: "registeredAt", type: "uint64" },
      { name: "passCount", type: "uint32" },
      { name: "approvalNonce", type: "uint32" },
      { name: "active", type: "bool" },
    ],
  },
] as const;

const STATE = ["unknown pass", "valid", "checked in", "expired", "revoked"] as const;
const TONE = ["unknown", "valid", "checkedin", "expired", "revoked"] as const;

const EXAMPLES: { label: string; id: `0x${string}`; note: string }[] = [
  {
    label: "ada-1",
    id: "0x1e5e5573eea8932933092fc636f163b54075026ab0bc470ec42dad24055e53ca",
    note: "issued, not yet checked in",
  },
  {
    label: "chen-1",
    id: "0xcc1fb73a375a757e4c8b331ef5dc60cbe4cad43e94eb00c8aa53d0de49875035",
    note: "checked in by the holder's ML-DSA-87 key",
  },
  {
    label: "boram-1",
    id: "0x81f49c48cfe419ce8fe60982c059d3e02817ef44109a364eefcfdb70c7081c27",
    note: "revoked by the issuer",
  },
];

function time(unix: bigint | undefined): string {
  if (!unix || unix === 0n) return "—";
  return new Date(Number(unix) * 1000).toISOString().replace("T", " ").slice(0, 16) + " UTC";
}

function short(hex: string | undefined, head = 10, tail = 6): string {
  if (!hex) return "—";
  return hex.length <= head + tail ? hex : `${hex.slice(0, head)}…${hex.slice(-tail)}`;
}

/** The account's EVM authorisation window, read over the native-lane REST API. */
function WindowStatus({ address }: { address: `0x${string}` }) {
  const { data, error, isLoading } = useQuery({
    queryKey: ["evm-window", address],
    queryFn: async () => {
      const res = await fetch(`/lcd-testnet/qorechain/pqc/v1/evm_window/${address}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return (await res.json()) as {
        found?: boolean;
        window?: { expiry_height?: string; max_txs?: number; used_txs?: number };
      };
    },
    retry: false,
    refetchInterval: 15_000,
  });
  if (isLoading) return <p className="muted">Reading the EVM window…</p>;
  if (error) return <p className="muted">Window status unavailable in this deployment (needs the REST proxy).</p>;
  if (!data?.found) return <p className="muted">No EVM window open for this account — sending is refused until one is opened.</p>;
  const w = data.window ?? {};
  return (
    <p className="muted">
      EVM window open until height {w.expiry_height ?? "?"} · {w.used_txs ?? 0}/{w.max_txs ?? "?"} transactions used
    </p>
  );
}

function PassCard({ passId }: { passId: `0x${string}` }) {
  const info = useReadContract({ address: REGISTRY, abi: ABI, functionName: "passInfo", args: [passId] });
  const state = useReadContract({ address: REGISTRY, abi: ABI, functionName: "passState", args: [passId] });

  if (info.isLoading || state.isLoading) return <p className="muted">Reading the registry…</p>;
  if (info.error) return <p className="bad">Could not read the registry: {info.error.message}</p>;

  const d = info.data;
  const code = Number(state.data ?? 0);
  if (!d || code === 0) {
    return (
      <div className="card">
        <h2>No such pass</h2>
        <p className="muted">QorePassRegistry has no record for {short(passId)}. Nothing was ever issued under this id.</p>
      </div>
    );
  }
  const [issuer, holder, eventId, metaHash, holderKeyHash, validUntil, issuedAt, checkedInAt] = d;

  return (
    <div className={`card verdict ${TONE[code]}`}>
      <div className="row">
        <h2>{STATE[code].toUpperCase()}</h2>
        <code>{short(passId)}</code>
      </div>
      <dl>
        <dt>Issuer</dt>
        <dd>
          <code>{issuer}</code>
        </dd>
        <dt>Holder key</dt>
        <dd>
          <code>keccak256(ML-DSA-87 pubkey) = {short(holderKeyHash, 12, 8)}</code>
        </dd>
        <dt>Event</dt>
        <dd>
          <code>{short(eventId, 12, 8)}</code>
        </dd>
        <dt>Metadata commitment</dt>
        <dd>
          <code>{short(metaHash, 12, 8)}</code>
        </dd>
        <dt>Issued</dt>
        <dd>{time(issuedAt)}</dd>
        <dt>Valid until</dt>
        <dd>{time(validUntil)}</dd>
        <dt>Checked in</dt>
        <dd>{time(checkedInAt)}</dd>
        <dt>Account binding</dt>
        <dd>
          <code>{holder === "0x0000000000000000000000000000000000000000" ? "none (key-bound pass)" : holder}</code>
        </dd>
      </dl>
      <p className="muted small">
        This verdict is <code>passState({short(passId, 8, 4)})</code> read from{" "}
        <a href={`https://explore.qore.network/address/${REGISTRY}`} target="_blank" rel="noreferrer">
          {REGISTRY}
        </a>{" "}
        on qorechain-diana. A checked-in pass got there through an ML-DSA-87 signature the chain verified with{" "}
        <code>pqcVerify</code>; a screenshot or a copied id cannot do it.
      </p>
    </div>
  );
}

function MyAccount({ address }: { address: `0x${string}` }) {
  const { data: balance } = useBalance({ address });
  const issuer = useReadContract({ address: REGISTRY, abi: ABI, functionName: "issuerInfo", args: [address] });
  const { signMessage, data: signature, isPending } = useSignMessage();
  const [scanned, setScanned] = useState<string>("");

  return (
    <div className="card">
      <h2>Your account</h2>
      <p>
        <code>{address}</code> · {balance ? `${formatEther(balance.value)} QOR` : "…"}
      </p>
      <WindowStatus address={address} />
      {issuer.data && issuer.data[5] ? (
        <p>
          You are a registered issuer: <strong>{issuer.data[3].toString()}</strong> passes issued, approval nonce{" "}
          {issuer.data[4].toString()}, key <code>{short(issuer.data[0], 10, 6)}</code>.
        </p>
      ) : (
        <p className="muted">This account is not a registered issuer.</p>
      )}

      <h3>Scan receipt (optional)</h3>
      <p className="muted small">
        A venue can keep a wallet-signed record of who scanned a pass and when. This is an EIP-191 signature from your
        EVM key — a classical signature, useful as a log, <em>not</em> the post-quantum check-in.
      </p>
      <div className="row">
        <input
          value={scanned}
          onChange={(e) => setScanned(e.target.value)}
          placeholder="pass id scanned at the door"
          spellCheck={false}
        />
        <button
          type="button"
          disabled={isPending || !scanned}
          onClick={() => signMessage({ message: `QorePass scan by ${address} at ${new Date().toISOString()} of ${scanned}` })}
        >
          {isPending ? "Signing…" : "Sign scan receipt"}
        </button>
      </div>
      {signature && (
        <p className="small">
          Signature <code>{short(signature, 18, 10)}</code>
        </p>
      )}
    </div>
  );
}

export function App() {
  const { address, chainId, isConnected } = useAccount();
  const { data: block } = useBlockNumber({ watch: true });
  const [input, setInput] = useState<string>(EXAMPLES[0].id);

  const passId = useMemo<`0x${string}` | null>(() => {
    const v = input.trim();
    return isHex(v) && size(v) === 32 ? (v as `0x${string}`) : null;
  }, [input]);

  return (
    <main>
      <header>
        <h1>
          Qore<span>Pass</span> verifier
        </h1>
        <p className="muted">
          Post-quantum event passes on QoreChain testnet ({qorechainTestnet.name}, chain {qorechainTestnet.id}). A pass
          is checked in by an ML-DSA-87 key, verified on chain — this page reads that record.
        </p>
        <ConnectButton showBalance={false} chainStatus="icon" />
      </header>

      <section className="card">
        <h2>Look up a pass</h2>
        <div className="row">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="0x… (bytes32 pass id)"
            spellCheck={false}
            aria-label="pass id"
          />
        </div>
        <div className="chips">
          {EXAMPLES.map((e) => (
            <button key={e.label} type="button" className="chip" onClick={() => setInput(e.id)} title={e.note}>
              {e.label}
            </button>
          ))}
        </div>
        {passId ? <PassCard passId={passId} /> : <p className="bad">That is not a 32-byte hex pass id.</p>}
      </section>

      {isConnected && address && chainId ? (
        <section>
          <MyAccount address={address} />
        </section>
      ) : (
        <p className="muted">
          Connect QoreX (or any injected wallet) to read your own account. The pass lookup above needs no wallet.
        </p>
      )}

      <footer>
        <p className="muted small">
          Latest block {block?.toString() ?? "…"} · registry <code>{REGISTRY}</code> ·{" "}
          <a href="https://github.com/dorithesky/qorepass-verify" target="_blank" rel="noreferrer">
            source
          </a>{" "}
          · scaffolded with <code>create-qorechain-dapp</code> (viem-wagmi template) and wired to the QoreX wallet via{" "}
          <code>@qorechain/qorex-rainbowkit</code>. Testnet only; nothing here has value.
        </p>
      </footer>
    </main>
  );
}

/** Unused import guard: keccak256/toHex are used by the holder-key helper below. */
export const holderKeyHash = (pubkey: `0x${string}`) => keccak256(toHex(pubkey));
