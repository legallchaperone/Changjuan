import { FileDown, LockKeyhole, Mic, Play, ShieldCheck } from "lucide-react";
import { AudioCitationButton } from "../components/AudioCitationButton";

const chapters = ["这个人是谁", "童年与家庭", "工作与迁徙", "家人记住的几件事", "待确认事实与原声附录"];

export default function H5Page() {
  return (
    <main>
      <section className="hero">
        <nav>
          <div className="mark">长卷</div>
          <a href="/entry">老人采访入口</a>
        </nav>
        <div className="hero-grid">
          <div>
            <h1>把爸妈讲过的话，做成句句有出处的家庭故事。</h1>
            <p>微信内完成采访、核验、二次同意、私密故事页和 PDF。事实必须能追溯到原声、照片或家人确认。</p>
            <div className="actions">
              <a className="primary" href="/entry"><Mic size={18} /> 开始采访</a>
              <a className="secondary" href="#story"><Play size={18} /> 查看故事页</a>
            </div>
          </div>
          <div className="story-visual" aria-label="story page preview">
            <div className="photo-strip">
              <span />
              <span />
              <span />
            </div>
            <h2>爸爸的故事</h2>
            <p>“1978 年，我进了县供销社。”</p>
            <AudioCitationButton />
            <div className="citation">Claim CJ-001 / 家人已确认 / 音频证据</div>
          </div>
        </div>
      </section>

      <section className="workflow" id="entry">
        <div className="step"><Mic /><strong>采访前同意</strong><span>文字或语音确认可回溯</span></div>
        <div className="step"><ShieldCheck /><strong>家人核验</strong><span>P0 事实必须处理</span></div>
        <div className="step"><LockKeyhole /><strong>二次同意</strong><span>发布前不可绕过</span></div>
        <div className="step"><FileDown /><strong>私密故事 + PDF</strong><span>隐藏 claims 不暴露</span></div>
      </section>

      <section className="story" id="story">
        <div className="story-copy">
          <h2>私密故事页</h2>
          <p>每段事实叙事绑定 claim IDs，未确认内容进入待确认区，不混入正文。</p>
        </div>
        <div className="chapter-list">
          {chapters.map((chapter, index) => (
            <div className="chapter" key={chapter}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{chapter}</strong>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
