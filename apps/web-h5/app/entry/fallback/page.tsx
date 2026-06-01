import { ArrowLeft, FileAudio, MessageCircle, ShieldCheck } from "lucide-react";

type FallbackPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function H5InterviewFallbackPage({ searchParams }: FallbackPageProps) {
  const params = (await searchParams) || {};
  const projectId = firstParam(params.project_id);
  const entryPath = `/entry${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`;
  const fallbackPath = `/entry/fallback${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`;

  return (
    <main className="entry-shell">
      <nav>
        <div className="mark">长卷</div>
        <a href={entryPath}>
          <ArrowLeft size={16} /> 返回微信入口
        </a>
      </nav>
      <section className="fallback-panel" data-fallback-path={fallbackPath}>
        <div className="entry-copy">
          <span className="eyebrow">H5 兜底采访</span>
          <h1>继续用 H5 采访，先保留同意和项目绑定。</h1>
          <p>
            当微信小程序无法唤起时，这里保留同一个项目的采访入口。运营可用项目编号核对同意记录、录音文件和后续上传状态。
          </p>
          <div className="actions">
            <a className="primary" href={entryPath}>
              <MessageCircle size={18} /> 重新打开微信入口
            </a>
            <a className="secondary" href="/">
              <FileAudio size={18} /> 查看故事页示例
            </a>
          </div>
        </div>
        <div className="entry-checklist" aria-label="fallback readiness">
          <FallbackStep icon={<ShieldCheck />} title="项目绑定" body={projectId ? `project_id: ${projectId}` : "未带 project_id 时返回入口创建项目。"} />
          <FallbackStep icon={<FileAudio />} title="证据保留" body="采访音频、转写和 consent evidence 仍按项目归档。" />
          <FallbackStep icon={<MessageCircle />} title="微信优先" body="小程序恢复后继续使用同一项目，不创建重复采访。" />
        </div>
      </section>
    </main>
  );
}

function FallbackStep({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
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
