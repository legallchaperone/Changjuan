"use client";

import { Pause, Play } from "lucide-react";
import { useState } from "react";

export function AudioCitationButton() {
  const [playing, setPlaying] = useState(false);

  return (
    <button
      type="button"
      aria-pressed={playing}
      aria-live="polite"
      onClick={() => setPlaying((value) => !value)}
    >
      {playing ? <Pause size={16} /> : <Play size={16} />}
      {playing ? "播放中 0:14:23" : "听原声 0:14:23"}
    </button>
  );
}
