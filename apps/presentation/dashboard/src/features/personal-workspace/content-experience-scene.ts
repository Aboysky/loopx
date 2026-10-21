import type {ExperiencePlan, ExperienceRun, ExperienceFrame} from "../../../../../../loopx/control_plane/capabilities/content_experience_contract";

export type ExperienceSceneRow = {label: string; run: ExperienceRun | null; index: number};
export function experienceSceneHeight(width: number, count: number) {return 100 + 258 * (width < 640 ? count : 1);}
export function experienceFrameFeedback(frame: ExperienceFrame, status: ExperienceRun["status"] | undefined, cn: boolean) {
  if (cn && !frame.applied && status === "budget_exhausted") return "剩余模型预算不足，状态与已用预算保持原值。";
  if (cn && !frame.applied && status === "action_unavailable") return "当前条件没有这一步的转移规则，状态保持原值。";
  return frame.feedback;
}

/** Draw only this model's own content. Recording never captures another page. */
export function drawExperienceScene(ctx: CanvasRenderingContext2D, width: number, height: number,
  model: ExperiencePlan, rows: ExperienceSceneRow[], digest: string, locale: string) {
  ctx.clearRect(0, 0, width, height); ctx.fillStyle = "#f5f6f8"; ctx.fillRect(0, 0, width, height);
  const text = (s: string, x: number, y: number, size: number, color = "#1a202c", maxWidth = width - x - 20, lines = 1) => {
    ctx.font = `${size >= 20 ? "600" : "400"} ${size}px system-ui, sans-serif`; ctx.fillStyle = color;
    const words = s.split(/\s+/u); let line = "", used = 0;
    for (const word of words) {
      const candidate = line ? `${line} ${word}` : word;
      if (ctx.measureText(candidate).width > maxWidth && line) {
        if (++used === lines) {ctx.fillText(`${line.slice(0, -1)}…`, x, y, maxWidth); return;}
        ctx.fillText(line, x, y, maxWidth); y += size * 1.4; line = word;
      } else line = candidate;
    }
    ctx.fillText(line, x, y, maxWidth);
  };
  text(model.title, 20, 31, width < 500 ? 19 : 23);
  text(model.boundary, 20, 54, 12, "#596272");
  const vertical = width < 640, gap = 12, cellWidth = vertical ? width - 32 : (width - 32 - gap * (rows.length - 1)) / rows.length;
  rows.forEach((row, i) => {
    const x = vertical ? 16 : 16 + i * (cellWidth + gap), y = 73 + (vertical ? i * 258 : 0);
    ctx.fillStyle = "#fff"; ctx.fillRect(x, y, cellWidth, 244); ctx.strokeStyle = "#d8dce3"; ctx.lineWidth = 1; ctx.strokeRect(x + .5, y + .5, cellWidth - 1, 243);
    const trace = row.run?.trace ?? [{state: model.initial_state, action: null, feedback: model.states.find(s => s.id === model.initial_state)!.description, spent: 0, applied: true}];
    const at = Math.min(row.index, trace.length - 1), frame = trace[at]!, state = model.states.find(s => s.id === frame.state)!;
    text(row.label, x + 15, y + 23, 14, "#596272", cellWidth - 30);
    const conditions = row.run ? model.parameters.map(p => p.choices.find(c => c.id === row.run!.parameters[p.id])!.label).join(" · ") : (locale === "zh-CN" ? "等待运行" : "Awaiting a run");
    text(conditions, x + 15, y + 44, 12, "#596272", cellWidth - 30, 2);
    text(state.label, x + 15, y + 88, cellWidth < 340 ? 23 : 28, "#165ed3", cellWidth - 30);
    text(experienceFrameFeedback(frame, row.run?.status, locale === "zh-CN"), x + 15, y + 115, 15, "#303a49", cellWidth - 30, 3);
    text(`${locale === "zh-CN" ? "模型用量" : "Model effort"} ${frame.spent} / ${model.budget} · ${at} ${locale === "zh-CN" ? "步" : "decisions"}`, x + 15, y + 201, 14, "#303a49", cellWidth - 30);
    const trail = trace.slice(Math.max(0, at - 3), at + 1).map(f => model.states.find(s => s.id === f.state)!.label).join(" → ");
    text(trail, x + 15, y + 224, 12, "#596272", cellWidth - 30);
  });
  text(`Source revision ${digest.slice(7, 19)} · model illustration`, 20, height - 12, 11, "#68717e");
}
