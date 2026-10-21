import {useRef, useState} from "react";
import {ContentMediaWorkbench} from "./content-media-workbench";
import {ContentExperienceWorkbench} from "./content-experience-workbench";
import {ContentReferenceWorkbench} from "./content-reference-workbench";
import {useWorkspaceI18n} from "./i18n";

/** One content outcome, with existing production and source paths preserved. */
export function ContentProductionWorkbench({goalId}: {goalId: string}) {
  const {locale} = useWorkspaceI18n(), cn = locale === "zh-CN";
  const [selected, setSelected] = useState(0), [recording, setRecording] = useState(false);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const labels = cn ? ["视频制作", "交互学习", "来源风格素材"] : ["Video production", "Interactive learning", "Source style references"];
  return <>
    <div className="content-production-tabs" role="tablist" aria-label={cn ? "内容制作形式" : "Content production format"}>{labels.map((label, i) => <button key={i} type="button" role="tab" id={`content-production-tab-${i}`} aria-selected={selected === i} aria-controls={`content-production-panel-${i}`} tabIndex={selected === i ? 0 : -1} disabled={recording}
      ref={el => {buttons.current[i] = el;}} onClick={() => setSelected(i)} onKeyDown={e => {
        const direction = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
        const next = e.key === "Home" ? 0 : e.key === "End" ? labels.length - 1 : direction ? (i + direction + labels.length) % labels.length : null;
        if (next !== null) {e.preventDefault(); setSelected(next); buttons.current[next]?.focus();}
      }}>{label}</button>)}</div>
    <section role="tabpanel" id={`content-production-panel-${selected}`} aria-labelledby={`content-production-tab-${selected}`}>
      {selected === 0 ? <ContentMediaWorkbench goalId={goalId} /> : selected === 1 ? <ContentExperienceWorkbench goalId={goalId} onRecordingChange={setRecording} /> : <ContentReferenceWorkbench />}
    </section>
  </>;
}
