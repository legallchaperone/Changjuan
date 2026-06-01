import { Headphones, MessageCircle, Mic, ShieldCheck } from "lucide-react";

type EntryPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function ElderEntryPage({ searchParams }: EntryPageProps) {
  const params = (await searchParams) || {};
  const projectId = firstParam(params.project_id);
  const miniprogramPath = projectId
    ? `pages/interview/interview?project_id=${encodeURIComponent(projectId)}`
    : "pages/project/project";
  const fallbackBasePath = "/entry/fallback";
  const fallbackPath = `${fallbackBasePath}${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`;
  const miniprogramFallbackPath = fallbackPath;
  const miniProgramLaunchUrl = `weixin://dl/business/?appid=wx_changjuan_phase1&path=${encodeURIComponent(miniprogramPath)}`;

  return (
    <main className="entry-shell">
      <nav>
        <div className="mark">长卷</div>
        <a href="/">返回首页</a>
      </nav>
      <section className="entry-panel">
        <div className="entry-copy">
          <span className="eyebrow">老人采访入口</span>
          <h1>打开微信采访页，先确认同意，再开始录音。</h1>
          <p>
            这个入口用于家庭成员把老人带到可追溯的采访流程。录音权限、采访同意、照片前置条件和中断恢复仍由小程序采访页执行。
          </p>
          <div className="actions">
            <a className="primary" href={miniProgramLaunchUrl}>
              <MessageCircle size={18} /> 打开微信小程序
            </a>
            <a className="secondary" href={miniprogramFallbackPath}>
              <Headphones size={18} /> H5 采访兜底入口
            </a>
          </div>
        </div>
        <div className="entry-checklist" aria-label="entry readiness">
          <EntryStep icon={<ShieldCheck />} title="同意先行" body="采访前必须完成文字或语音同意，证据可回溯。" />
          <EntryStep icon={<Mic />} title="录音权限" body="进入采访页后检查微信录音权限，弱网可恢复缺失 chunk。" />
          <EntryStep icon={<MessageCircle />} title="项目绑定" body={projectId ? `project_id: ${projectId}` : "未带 project_id 时先创建项目。"} />
        </div>
      </section>
    </main>
  );
}

function EntryStep({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <div className="entry-step">
      {icon}
      <strong>{title}</strong>
      <span>{body}</span>
    </div>
  );
}

function firstParam(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}
