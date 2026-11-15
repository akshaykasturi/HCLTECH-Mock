// "How this was decided": the six checks a ticket passes through, drawn as a vertical route.
// If the gate stops a ticket, the line turns red at that station and the stations after it show "Not run".
import { buildStations, NAMES } from "../lib/stations";
import { pct } from "../lib/words";

function Meter({ value, weakest }) {
  return (
    <div className="mt-1.5 flex items-center gap-2">
      <div className="h-1.5 w-28 overflow-hidden rounded-full bg-rule" aria-hidden="true">
        <div className={`h-full ${weakest ? "bg-hold" : "bg-route"}`} style={{ width: pct(value) }} />
      </div>
      <span className="text-[13px] text-steel">
        {pct(value)}
        {weakest && <span className="ml-1.5 text-hold">lowest signal, sets overall confidence</span>}
      </span>
    </div>
  );
}

export default function RouteTrack({ result, animate = true }) {
  const stations = result ? buildStations(result) : NAMES.map((name) => ({ name, state: "idle" }));
  const stopIndex = stations.findIndex((s) => s.state === "stopped");
  const tone = stopIndex !== -1 ? stations[stopIndex].tone : "stop";
  const TONE = { stop: { bg: "bg-stop", border: "border-stop", text: "text-stop" }, hold: { bg: "bg-hold", border: "border-hold", text: "text-hold" } }[tone];

  return (
    <ol className="relative" aria-label="How this was decided">
      {stations.map((s, i) => {
        const after = stopIndex !== -1 && i > stopIndex;
        const line = s.state === "idle" ? "bg-rule" : after ? "bg-rule" : i === stopIndex ? TONE.bg : "bg-route";
        const dot =
          s.state === "stopped" ? `${TONE.border} ${TONE.bg}`
            : s.state === "skipped" || s.state === "idle" ? "border-rule bg-paper"
              : "border-route bg-sheet";
        return (
          <li key={s.name} className="relative grid grid-cols-[28px_1fr] gap-x-3 pb-5 last:pb-0">
            {i < stations.length - 1 && (
              <span
                className={`absolute left-[13px] top-[18px] h-[calc(100%-10px)] w-[2px] ${line} ${animate && result ? "route-draw" : ""}`}
                style={animate && result ? { animationDelay: `${i * 90}ms` } : undefined}
                aria-hidden="true"
              />
            )}
            <span className={`relative z-10 mt-[3px] grid h-[16px] w-[16px] place-items-center justify-self-center rounded-full border-2 ${dot}`}>
              {s.state === "stopped" && <span className="h-[6px] w-[6px] rounded-[1px] bg-white" />}
            </span>
            <div className={s.state === "skipped" || s.state === "idle" ? "text-steel" : ""}>
              <p className="text-[13px] text-steel">
                <span className="mr-1.5 text-steel/70">{i + 1}</span>
                {s.name}
              </p>
              {s.text && (
                <p className={`mt-0.5 text-[15px] leading-snug ${s.state === "stopped" ? `font-semibold ${TONE.text}` : ""}`}>
                  {s.text}
                </p>
              )}
              {s.note && <p className="mt-0.5 text-[13px] text-steel">{s.note}</p>}
              {s.meter !== undefined && s.state !== "idle" && <Meter value={s.meter} weakest={s.weakest} />}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
