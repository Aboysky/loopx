import {useEffect, useRef, useState, type ReactNode} from "react";
import {Button} from "../../components/ui/button";
import {fetchAppStewardTarget, type BoundConversationTarget} from "../../data/chat";
import {useWorkspaceI18n} from "./i18n";

/** Only mount at the local, unbound manager Chat entry. Children must not mount
 * until discovery finishes: they otherwise expose the ordinary manager queue.
 * Once opened, the route freezes the exact Session and this boundary unmounts.
 */
export function AppStewardEntry({children, onOpen}: {children: ReactNode; onOpen: (target: BoundConversationTarget) => void}) {
  const {locale} = useWorkspaceI18n();
  const zh = locale === "zh-CN";
  const [state, setState] = useState<"loading" | "ordinary" | "unavailable">("loading");
  const [revision, setRevision] = useState(0);
  const open = useRef(onOpen);
  open.current = onOpen;
  useEffect(() => {
    const changed = () => {setState("loading"); setRevision(value => value + 1);};
    window.addEventListener("loopx:app-steward-changed", changed);
    return () => window.removeEventListener("loopx:app-steward-changed", changed);
  }, []);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    void fetchAppStewardTarget(controller.signal).then(target => {
      if (!active) return;
      if (target) open.current(target);
      else setState("ordinary");
    }).catch(() => {if (active) setState("unavailable");}).finally(() => clearTimeout(timeout));
    return () => {active = false; controller.abort(); clearTimeout(timeout);};
  }, [revision]);
  if (state === "ordinary") return children;
  const settings = new URL(window.location.href);
  settings.searchParams.set("view", "overview");
  settings.searchParams.set("settings_scope", "machine");
  settings.searchParams.set("settings_tab", "lark");
  return <main className="mx-auto flex min-h-dvh max-w-xl flex-col justify-center gap-5 p-6 text-slate-900 dark:text-zinc-100">
    <h1 className="text-xl font-semibold">{zh ? "LoopX 管家" : "LoopX steward"}</h1>
    {state === "loading" ? <p role="status">{zh ? "正在打开原管家会话…" : "Opening the original steward conversation…"}</p> : <>
      <p role="alert">{zh ? "原管家会话暂不可用。请检查所选连接后重试。" : "The original steward conversation is unavailable. Check the selected connection and retry."}</p>
      <div className="flex flex-wrap gap-3">
        <Button onClick={() => {setState("loading"); setRevision(value => value + 1);}}>{zh ? "重试" : "Retry"}</Button>
        <a className="inline-flex min-h-9 items-center underline underline-offset-4" href={settings.href}>{zh ? "打开会话设置" : "Open conversation settings"}</a>
      </div>
    </>}
  </main>;
}
