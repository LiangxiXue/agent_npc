import { useEffect, useMemo, useState } from "react";
import {
  Archive,
  Bot,
  Bug,
  ChevronDown,
  Download,
  Eye,
  Map as MapIcon,
  Package,
  RotateCcw,
  ScrollText,
  Send,
  Sparkles,
  Swords,
  Trash2,
  Wand2
} from "lucide-react";

type RetrievalMode = "typed" | "hybrid" | "semantic" | "legacy" | "off";

type Npc = {
  npc_id: string;
  name: string;
  role: string;
  description: string;
  description_zh?: string;
  hidden_alignment: string;
  mood: string;
  trust: number;
  affection: number;
};

type Quest = {
  quest_id: string;
  npc_id: string;
  title: string;
  description: string;
  status: string;
};

type Player = {
  location: string;
  inventory: string[];
  unlocked_locations: string[];
};

type Interaction = {
  id: number;
  npc_id: string;
  player_input: string;
  player_input_zh?: string;
  npc_response: string;
  npc_response_zh?: string;
  created_at: string;
};

type Memory = {
  id?: number;
  memory_type?: string;
  content?: string;
  content_zh?: string;
  tags?: string[];
  retrieval_score?: number;
  semantic_score?: number;
  retrieval_reason?: string;
  retrieval_reason_zh?: string;
};

type WorldEvent = {
  id: number;
  content: string;
  content_zh?: string;
  created_at: string;
};

type ClientState = {
  npcs: Npc[];
  selected_npc: Npc;
  selected_quest: Quest;
  quests: Quest[];
  player: Player;
  memories: Memory[];
  recent_interactions: Interaction[];
  interaction_logs: Record<string, unknown>[];
  world_events: WorldEvent[];
  runtime: Record<string, unknown>;
  retrieval_modes: { value: RetrievalMode; label: string }[];
  suggested_inputs: string[];
};

type AgentRun = {
  npc_id: string;
  player_input: string;
  player_input_zh?: string;
  npc_response: string;
  npc_response_zh?: string;
  retrieved_lore: Record<string, unknown>[];
  retrieved_memories: Record<string, unknown>[];
  recent_context: Record<string, unknown>[];
  state_snapshot: Record<string, unknown>;
  decision: Record<string, unknown>;
  tool_calls: Record<string, unknown>[];
  memory_policy: Record<string, unknown>;
  memory_writes: Record<string, unknown>[];
  state_changes: Record<string, unknown>[];
  workflow_steps: Record<string, unknown>[];
  timings: Record<string, number>;
};

type Preview = {
  preview_mode: "full";
  retrieved_lore: Record<string, unknown>[];
  retrieved_memories: Record<string, unknown>[];
  timings: Record<string, number>;
};

type SceneLocation = {
  id: string;
  name: string;
  title: string;
  image: string;
  idleText: string;
};

const assetBase = "/assets/pixel";

const npcAssets: Record<string, string> = {
  lina: `${assetBase}/npc-lina.png`,
  ron: `${assetBase}/npc-ron.png`,
  mira: `${assetBase}/npc-mira.png`,
  sable: `${assetBase}/npc-sable.png`
};

const npcLocations: Record<string, string> = {
  lina: "tavern",
  ron: "guard-post",
  mira: "ruins-entrance",
  sable: "grayhaven-town"
};

const locationNpcs = Object.fromEntries(
  Object.entries(npcLocations).map(([npcId, locationId]) => [locationId, npcId])
) as Record<string, string>;

const locations: SceneLocation[] = [
  {
    id: "grayhaven-town",
    name: "Grayhaven",
    title: "城镇广场",
    image: `${assetBase}/map-grayhaven-town.png`,
    idleText: "广场上人声稀疏，Sable 正在观察来往的行人。"
  },
  {
    id: "tavern",
    name: "Tavern",
    title: "Lina 的酒馆",
    image: `${assetBase}/map-tavern.png`,
    idleText: "酒馆灯还亮着。"
  },
  {
    id: "guard-post",
    name: "Gate Post",
    title: "镇门守卫岗",
    image: `${assetBase}/map-guard-post.png`,
    idleText: "镇门火把噼啪作响，Ron 仍守在岗哨前。"
  },
  {
    id: "ruins-entrance",
    name: "Ruins",
    title: "地下遗迹入口",
    image: `${assetBase}/map-ruins-entrance.png`,
    idleText: "遗迹入口传来潮湿的冷风，Mira 正翻看旧笔记。"
  }
];

const itemAssets: Record<string, { label: string; image: string }> = {
  copper_key: { label: "铜钥匙", image: `${assetBase}/item-copper-key.png` },
  tavern_discount_coupon: { label: "酒馆折扣券", image: `${assetBase}/item-tavern-coupon.png` },
  guard_badge: { label: "守卫徽章", image: `${assetBase}/item-guard-badge.png` },
  ancient_notes: { label: "遗迹笔记", image: `${assetBase}/item-ruins-notes.png` },
  relic_tip: { label: "古物线索", image: `${assetBase}/item-relic-tip.png` }
};

const translationCache = new Map<string, string>();

export function App() {
  const [clientState, setClientState] = useState<ClientState | null>(null);
  const [selectedNpcId, setSelectedNpcId] = useState("lina");
  const [selectedLocationId, setSelectedLocationId] = useState("tavern");
  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>("hybrid");
  const [playerInput, setPlayerInput] = useState("");
  const [lastRun, setLastRun] = useState<AgentRun | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [developerOpen, setDeveloperOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadBootstrap(selectedNpcId);
  }, [selectedNpcId]);

  useEffect(() => {
    setSelectedLocationId(npcLocations[selectedNpcId] ?? "grayhaven-town");
  }, [selectedNpcId]);

  const selectedLocation = useMemo(
    () => locations.find((location) => location.id === selectedLocationId) ?? locations[0],
    [selectedLocationId]
  );

  const conversation = clientState?.recent_interactions ?? [];
  const selectedNpc = clientState?.selected_npc;
  const selectedQuest = clientState?.selected_quest;

  async function loadBootstrap(npcId: string) {
    setBusy(true);
    setError(null);
    try {
      const data = await api<ClientState>(`/api/bootstrap?npc_id=${encodeURIComponent(npcId)}`);
      setClientState(data);
    } catch (reason) {
      setError(getErrorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  function selectLocation(locationId: string) {
    setSelectedLocationId(locationId);
    const npcId = locationNpcs[locationId];
    if (npcId && npcId !== selectedNpcId) {
      setSelectedNpcId(npcId);
      setLastRun(null);
      setPreview(null);
    }
  }

  async function sendTurn() {
    const input = playerInput.trim();
    if (!input) return;
    setBusy(true);
    setError(null);
    try {
      const data = await api<{ run: AgentRun; state: ClientState }>("/api/turn", {
        method: "POST",
        body: JSON.stringify({
          npc_id: selectedNpcId,
          player_input: input,
          retrieval_mode: retrievalMode
        })
      });
      setLastRun(data.run);
      setClientState(data.state);
      setPreview(null);
      setPlayerInput("");
    } catch (reason) {
      setError(getErrorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function previewRetrieval() {
    const input = playerInput.trim();
    if (!input) return;
    setBusy(true);
    setError(null);
    try {
      const data = await api<Preview>("/api/retrieve-preview", {
        method: "POST",
        body: JSON.stringify({
          npc_id: selectedNpcId,
          player_input: input,
          retrieval_mode: retrievalMode,
          preview_mode: "full"
        })
      });
      setPreview(data);
      setDeveloperOpen(true);
    } catch (reason) {
      setError(getErrorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function resetState() {
    setBusy(true);
    setError(null);
    try {
      const data = await api<ClientState>("/api/reset", { method: "POST" });
      setSelectedNpcId("lina");
      setClientState(data);
      setLastRun(null);
      setPreview(null);
      setPlayerInput("");
    } catch (reason) {
      setError(getErrorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function clearChat() {
    setBusy(true);
    setError(null);
    try {
      const data = await api<ClientState>("/api/clear-chat", {
        method: "POST",
        body: JSON.stringify({ npc_id: selectedNpcId })
      });
      setClientState(data);
      setLastRun(null);
      setPreview(null);
    } catch (reason) {
      setError(getErrorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function rebuildIndex() {
    setBusy(true);
    setError(null);
    try {
      const data = await api<{ state: ClientState }>("/api/rebuild-index", {
        method: "POST",
        body: JSON.stringify({ npc_id: selectedNpcId })
      });
      setClientState(data.state);
    } catch (reason) {
      setError(getErrorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  function downloadTrace() {
    window.open("/api/trace", "_blank", "noopener,noreferrer");
  }

  if (!clientState || !selectedNpc || !selectedQuest) {
    return (
      <main className="loading-screen">
        <div className="pixel-loader" />
        <p>Loading Grayhaven...</p>
        {error && <p className="error-text">{error}</p>}
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Memory-Driven NPC Agent</p>
          <h1>Grayhaven</h1>
        </div>
        <div className="topbar-actions">
          <select
            value={retrievalMode}
            onChange={(event) => setRetrievalMode(event.target.value as RetrievalMode)}
            aria-label="Memory retrieval mode"
          >
            {clientState.retrieval_modes.map((mode) => (
              <option key={mode.value} value={mode.value}>
                {mode.label}
              </option>
            ))}
          </select>
          <button className="icon-button" onClick={resetState} title="重置状态" aria-label="重置状态">
            <RotateCcw size={18} />
          </button>
          <button className="icon-button" onClick={clearChat} title="清空对话" aria-label="清空对话">
            <Trash2 size={18} />
          </button>
          <button className="icon-button" onClick={downloadTrace} title="导出 trace" aria-label="导出 trace">
            <Download size={18} />
          </button>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <section className="game-grid">
        <aside className="panel npc-panel">
          <div className="panel-title">
            <Bot size={17} />
            <span>Characters</span>
          </div>
          <div className="npc-list">
            {clientState.npcs.map((npc) => (
              <button
                className={`npc-chip ${npc.npc_id === selectedNpcId ? "active" : ""}`}
                key={npc.npc_id}
                onClick={() => setSelectedNpcId(npc.npc_id)}
              >
                <img src={npcAssets[npc.npc_id]} alt="" />
                <span>{npc.name}</span>
              </button>
            ))}
          </div>

          <div className="portrait-frame">
            <img src={npcAssets[selectedNpc.npc_id]} alt={selectedNpc.name} />
          </div>
          <h2>{selectedNpc.name}</h2>
          <p className="role">{selectedNpc.role}</p>
          <p className="description">{selectedNpc.description}</p>
          <TranslatedLine
            text={selectedNpc.description_zh}
            original={selectedNpc.description}
            source={`npc:${selectedNpc.npc_id}:description`}
          />
          <StatBar label="Trust" value={selectedNpc.trust} tone="trust" />
          <StatBar label="Affection" value={selectedNpc.affection} tone="affection" />
          <div className="quest-card">
            <ScrollText size={16} />
            <div>
              <strong>{selectedQuest.title}</strong>
              <span>{selectedQuest.status}</span>
            </div>
          </div>
        </aside>

        <section className="stage-panel">
          <div className="scene-frame">
            <img src={selectedLocation.image} alt={selectedLocation.title} />
            <div className="scene-label">
              <span>{selectedLocation.name}</span>
              <strong>{selectedLocation.title}</strong>
            </div>
          </div>

          <div className="dialogue-window">
            <div className="dialogue-feed">
              {conversation.length === 0 ? (
                <div className="empty-dialogue">
                  <Sparkles size={24} />
                  <span>{selectedLocation.idleText}</span>
                </div>
              ) : (
                conversation.map((turn) => (
                  <div className="turn-pair" key={turn.id}>
                    <Bubble speaker="Player" text={turn.player_input} />
                    <Bubble
                      speaker={selectedNpc.name}
                      text={turn.npc_response}
                      translation={turn.npc_response_zh}
                      source={`interaction:${turn.id}:npc_response`}
                      npc
                    />
                  </div>
                ))
              )}
            </div>
            <div className="prompt-row">
              {clientState.suggested_inputs.slice(0, 3).map((suggestion) => (
                <button key={suggestion} onClick={() => setPlayerInput(suggestion)}>
                  {suggestion}
                </button>
              ))}
            </div>
            <div className="input-row">
              <textarea
                value={playerInput}
                onChange={(event) => setPlayerInput(event.target.value)}
                placeholder={`对 ${selectedNpc.name} 说些什么...`}
              />
              <div className="send-actions">
                <button className="secondary-action" onClick={previewRetrieval} disabled={busy || !playerInput.trim()}>
                  <Eye size={17} />
                  <span>Preview</span>
                </button>
                <button className="primary-action" onClick={sendTurn} disabled={busy || !playerInput.trim()}>
                  <Send size={17} />
                  <span>{busy ? "Running" : "Send"}</span>
                </button>
              </div>
            </div>
          </div>
        </section>

        <aside className="panel world-panel">
          <div className="panel-title">
            <MapIcon size={17} />
            <span>Map</span>
          </div>
          <div className="location-grid">
            {locations.map((location) => (
              <button
                key={location.id}
                className={`location-card ${location.id === selectedLocationId ? "active" : ""}`}
                onClick={() => selectLocation(location.id)}
              >
                <img src={location.image} alt="" />
                <span>{location.title}</span>
              </button>
            ))}
          </div>

          <div className="panel-title inline-title">
            <Package size={17} />
            <span>Inventory</span>
          </div>
          <div className="inventory-grid">
            {clientState.player.inventory.length === 0 ? (
              <div className="item-slot muted-slot empty-inventory">
                <img src={`${assetBase}/item-empty-slot.png`} alt="" />
                <span>暂无物品</span>
              </div>
            ) : (
              clientState.player.inventory.map((item) => {
                const asset = itemAssets[item];
                return (
                  <div className={`item-slot ${asset ? "" : "muted-slot"}`} key={item}>
                    <img src={asset?.image ?? `${assetBase}/item-empty-slot.png`} alt="" />
                    <span>{asset?.label ?? item}</span>
                  </div>
                );
              })
            )}
          </div>

          <div className="panel-title inline-title">
            <Archive size={17} />
            <span>Memory</span>
          </div>
          <div className="memory-list">
            {clientState.memories.length === 0 ? (
              <p className="subtle">暂无长期记忆。</p>
            ) : (
              clientState.memories.slice(0, 4).map((memory, index) => (
                <article className="memory-entry" key={`${memory.id ?? index}-${memory.content}`}>
                  <strong>{memory.memory_type ?? "memory"}</strong>
                  <span>{memory.content}</span>
                  <TranslatedLine
                    text={memory.content_zh}
                    original={memory.content}
                    source={`client_memory:${memory.id ?? index}:content`}
                    compact
                  />
                </article>
              ))
            )}
          </div>

          <div className="panel-title inline-title">
            <Swords size={17} />
            <span>World</span>
          </div>
          <div className="event-list">
            {clientState.world_events.length === 0 ? (
              <p className="subtle">暂无世界事件。</p>
            ) : (
              clientState.world_events.slice(0, 4).map((event) => (
                <article className="event-entry" key={event.id}>
                  <span>{event.content}</span>
                  <TranslatedLine
                    text={event.content_zh}
                    original={event.content}
                    source={`world_event:${event.id}:content`}
                    compact
                  />
                </article>
              ))
            )}
          </div>
        </aside>
      </section>

      <section className={`developer-drawer ${developerOpen ? "open" : ""}`}>
        <button className="drawer-toggle" onClick={() => setDeveloperOpen((value) => !value)}>
          <Bug size={17} />
          <span>Developer Trace</span>
          <ChevronDown size={18} />
        </button>
        <div className="drawer-content">
          <button className="secondary-action compact" onClick={rebuildIndex} disabled={busy}>
            <Wand2 size={16} />
            <span>Rebuild Index</span>
          </button>
          <TraceGrid lastRun={lastRun} preview={preview} runtime={clientState.runtime} />
        </div>
      </section>
    </main>
  );
}

function Bubble({
  speaker,
  text,
  translation,
  source,
  npc = false
}: {
  speaker: string;
  text: string;
  translation?: string;
  source?: string;
  npc?: boolean;
}) {
  return (
    <article className={`bubble ${npc ? "npc-bubble" : "player-bubble"}`}>
      <span>{speaker}</span>
      <p>{text}</p>
      <TranslatedLine text={translation} original={text} source={source} />
    </article>
  );
}

function TranslatedLine({
  text,
  original,
  source,
  compact = false
}: {
  text?: string;
  original?: string;
  source?: string;
  compact?: boolean;
}) {
  const [translation, setTranslation] = useState(text ?? "");

  useEffect(() => {
    let cancelled = false;
    if (text || !source || !original || !looksTranslatable(original)) {
      setTranslation(text ?? "");
      return;
    }
    const cacheKey = `${source}:${original}`;
    const cached = translationCache.get(cacheKey);
    if (cached) {
      setTranslation(cached);
      return;
    }
    void api<{ status: string; translated_text?: string }>("/api/translate-debug", {
      method: "POST",
      body: JSON.stringify({ source, text: original })
    })
      .then((result) => {
        if (cancelled) return;
        if ((result.status === "translated" || result.status === "cached") && result.translated_text) {
          translationCache.set(cacheKey, result.translated_text);
          setTranslation(result.translated_text);
        }
      })
      .catch(() => {
        if (!cancelled) setTranslation("");
      });
    return () => {
      cancelled = true;
    };
  }, [text, original, source]);

  if (!translation) return null;
  return (
    <p className={`translation-line ${compact ? "compact-translation" : ""}`}>
      <strong>中文辅助</strong>
      {translation}
    </p>
  );
}

function StatBar({ label, value, tone }: { label: string; value: number; tone: "trust" | "affection" }) {
  return (
    <div className="stat-block">
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <div className="bar-track">
        <i className={tone} style={{ width: `${Math.max(0, Math.min(value, 100))}%` }} />
      </div>
    </div>
  );
}

function TraceGrid({
  lastRun,
  preview,
  runtime
}: {
  lastRun: AgentRun | null;
  preview: Preview | null;
  runtime: Record<string, unknown>;
}) {
  const panels = [
    ["retrieved_lore", lastRun?.retrieved_lore ?? preview?.retrieved_lore ?? []],
    ["retrieved_memories", lastRun?.retrieved_memories ?? preview?.retrieved_memories ?? []],
    ["state_snapshot", lastRun?.state_snapshot ?? {}],
    ["recent_context", lastRun?.recent_context ?? []],
    ["tool_calls", lastRun?.tool_calls ?? []],
    ["memory_policy", lastRun?.memory_policy ?? {}],
    ["decision", lastRun?.decision ?? {}],
    ["timings", lastRun?.timings ?? preview?.timings ?? {}],
    ["runtime", runtime]
  ] as const;

  return (
    <>
      <TranslatedTraceSummary lastRun={lastRun} preview={preview} />
      <div className="trace-grid">
        {panels.map(([title, value]) => (
          <details key={title}>
            <summary>{title}</summary>
            <pre>{JSON.stringify(value, null, 2)}</pre>
          </details>
        ))}
      </div>
    </>
  );
}

function TranslatedTraceSummary({ lastRun, preview }: { lastRun: AgentRun | null; preview: Preview | null }) {
  const lore = (lastRun?.retrieved_lore ?? preview?.retrieved_lore ?? []) as Record<string, unknown>[];
  const memories = (lastRun?.retrieved_memories ?? preview?.retrieved_memories ?? []) as Record<string, unknown>[];
  const workflow = (lastRun?.workflow_steps ?? []) as Record<string, unknown>[];
  const memoryWrites = (lastRun?.memory_writes ?? []) as Record<string, unknown>[];
  const hasEvidence =
    lore.some((item) => getString(item, "excerpt")) ||
    memories.some((item) => getString(item, "content")) ||
    workflow.some((item) => getString(item, "result")) ||
    memoryWrites.some((item) => getString(getRecord(item, "arguments"), "content"));

  if (!hasEvidence) {
    return <p className="trace-help">中文辅助翻译会在后端 LLM 配置可用时显示；原始 trace 仍保留在下方 JSON 中。</p>;
  }

  return (
    <div className="translated-trace">
      {lore.slice(0, 3).map((item, index) => (
        <TraceEvidenceCard
          key={`lore-${getString(item, "lore_id") || index}`}
          label="Lore"
          title={getString(item, "title") || getString(item, "lore_id") || "lore"}
          original={getString(item, "excerpt")}
          translation={getString(item, "excerpt_zh")}
          source={`trace_lore:${getString(item, "lore_id") || index}:excerpt`}
        />
      ))}
      {memories.slice(0, 3).map((item, index) => (
        <TraceEvidenceCard
          key={`memory-${getString(item, "id") || index}`}
          label={getString(item, "memory_type") || "Memory"}
          title={getString(item, "retrieval_score") ? `score ${getString(item, "retrieval_score")}` : "Retrieved memory"}
          original={getString(item, "content")}
          translation={getString(item, "content_zh")}
          source={`trace_memory:${getString(item, "id") || index}:content`}
        />
      ))}
      {workflow.slice(0, 4).map((step, index) => (
        <TraceEvidenceCard
          key={`workflow-${getString(step, "stage") || index}`}
          label="Workflow"
          title={getString(step, "stage") || "step"}
          original={getString(step, "result")}
          translation={getString(step, "result_zh")}
          source={`trace_workflow:${getString(step, "stage") || index}:result`}
        />
      ))}
      {memoryWrites.slice(0, 3).map((write, index) => {
        const args = getRecord(write, "arguments");
        return (
          <TraceEvidenceCard
            key={`write-${index}`}
            label="Memory Write"
            title={getString(args, "memory_type") || "memory"}
            original={getString(args, "content")}
            translation={getString(args, "content_zh")}
            source={`trace_memory_write:${index}:content`}
          />
        );
      })}
    </div>
  );
}

function TraceEvidenceCard({
  label,
  title,
  original,
  translation,
  source
}: {
  label: string;
  title: string;
  original: string;
  translation: string;
  source: string;
}) {
  if (!original) return null;
  return (
    <article className="trace-translation-card">
      <span>{label}</span>
      <strong>{title}</strong>
      <p>{original}</p>
      <TranslatedLine text={translation} original={original} source={source} />
    </article>
  );
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {})
    },
    ...init
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return (await response.json()) as T;
}

function getErrorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}

function getString(item: Record<string, unknown> | undefined, key: string): string {
  const value = item?.[key];
  if (value === undefined || value === null) return "";
  return String(value);
}

function getRecord(item: Record<string, unknown>, key: string): Record<string, unknown> {
  const value = item[key];
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function looksTranslatable(text: string): boolean {
  return /[A-Za-z]/.test(text) && !/[\u3400-\u9fff]/.test(text);
}
