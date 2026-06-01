import { ChangjuanClient } from "@changjuan/clients";
import type {
  AlertRecord,
  HouseholdOpsExport,
  PilotMetrics,
  ProjectSummary,
  SupportTicket,
} from "@changjuan/shared-types";
import { AlertTriangle, AudioLines, CheckCircle2, ClipboardCheck, CreditCard, ShieldCheck } from "lucide-react";
import { retryTaskAction } from "./actions";
import { RetryTaskButton } from "../components/RetryTaskButton";

export const dynamic = "force-dynamic";

type AdminDashboardData = {
  metrics: PilotMetrics;
  projects: ProjectSummary[];
  householdOps: HouseholdOpsExport;
  supportTickets: SupportTicket[];
  stuckProjects: ProjectSummary[];
  alerts: AlertRecord[];
  loadErrors: string[];
  configured: boolean;
};

const emptyMetrics: PilotMetrics = {
  households_total: 0,
  completion_rate: 0,
  effective_interview_completion_rate: 0,
  family_correction_completion_rate: 0,
  major_fact_error_complaint_rate: 0,
  recommend_rate: 0,
  nps: null,
  manual_minutes_per_household: null,
  deposit_rate: 0,
  feedback_count: 0,
};

const emptyDashboard: AdminDashboardData = {
  metrics: emptyMetrics,
  projects: [],
  householdOps: { households: [] },
  supportTickets: [],
  stuckProjects: [],
  alerts: [],
  loadErrors: [],
  configured: false,
};

const fallbackTaskId = "00000000-0000-4000-8000-000000000001";

export default async function AdminPage() {
  const dashboard = await loadAdminDashboard();
  const firstHousehold = dashboard.householdOps.households[0];
  const totalAiCost = dashboard.householdOps.households.reduce((sum, row) => sum + row.ai_cost_cents, 0);
  const manualInterventions = dashboard.householdOps.households.reduce(
    (sum, row) => sum + row.manual_intervention_count,
    0,
  );

  return (
    <main className="admin-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">卷</div>
          <div>
            <strong>长卷</strong>
            <span>Phase 1 Ops</span>
          </div>
        </div>
        <nav>
          <a className="active">项目</a>
          <a>Claim 审核</a>
          <a>敏感队列</a>
          <a>支付标记</a>
          <a>Pilot Metrics</a>
          <a>删除请求</a>
        </nav>
      </aside>
      <section className="workspace">
        <header className="topbar">
          <div>
            <h1>运营控制台</h1>
            <p>项目状态、证据链、核验风险和人工处理时长集中处理。</p>
          </div>
          <RetryTaskButton action={retryTaskAction} defaultTaskId={dashboard.alerts[0]?.alert_id || fallbackTaskId} />
        </header>

        {!dashboard.configured ? (
          <section className="banner" role="status">
            设置 <code>ADMIN_API_TOKEN</code> 后，本页会读取真实 Phase 1 admin API；当前显示空状态。
          </section>
        ) : null}
        {dashboard.loadErrors.length ? (
          <section className="banner danger-banner" role="alert">
            {dashboard.loadErrors.join(" / ")}
          </section>
        ) : null}

        <section className="metrics" aria-label="pilot metrics">
          <Metric icon={<CheckCircle2 />} label="完成率" value={percent(dashboard.metrics.completion_rate)} target="目标 ≥70%" />
          <Metric
            icon={<ClipboardCheck />}
            label="家人核验"
            value={percent(dashboard.metrics.family_correction_completion_rate)}
            target="目标 ≥70%"
          />
          <Metric
            icon={<ShieldCheck />}
            label="推荐率 / NPS"
            value={`${percent(dashboard.metrics.recommend_rate)} / ${dashboard.metrics.nps ?? "NA"}`}
            target="推荐 ≥80%，NPS >50"
          />
          <Metric icon={<CreditCard />} label="押金占比" value={percent(dashboard.metrics.deposit_rate)} target="目标 ≥30%" />
        </section>

        <section className="split">
          <div className="panel">
            <div className="panel-title">
              <h2>项目队列</h2>
              <span>{dashboard.projects.length} 户 pilot tracking</span>
            </div>
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>项目</th>
                  <th>状态</th>
                  <th>支付</th>
                  <th>Owner</th>
                  <th>风险</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.projects.map((project) => (
                  <tr key={project.project_id}>
                    <td>{shortId(project.project_id)}</td>
                    <td>{project.title}</td>
                    <td>{project.status}</td>
                    <td>{paymentLabel(project)}</td>
                    <td>{project.ops_owner_id || "未分配"}</td>
                    <td>{project.stuck_reason || project.story_page_id || "无阻塞"}</td>
                  </tr>
                ))}
                {!dashboard.projects.length ? (
                  <tr>
                    <td colSpan={6}>暂无项目数据</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <div className="panel">
            <div className="panel-title">
              <h2>Ops Gates</h2>
              <span>publish 不可绕过</span>
            </div>
            <div className="gate-list">
              <Gate name="Effective interview" value={percent(dashboard.metrics.effective_interview_completion_rate)} tone="warn" />
              <Gate name="Major fact complaints" value={percent(dashboard.metrics.major_fact_error_complaint_rate)} tone="block" />
              <Gate name="Manual minutes / household" value={minutes(dashboard.metrics.manual_minutes_per_household)} tone="warn" />
              <Gate name="Feedback count" value={String(dashboard.metrics.feedback_count)} tone="ok" />
            </div>
            <div className="audio-review">
              <AudioLines />
              <div>
                <strong>音频 / 转写回放</strong>
                <p>{firstHousehold ? `${firstHousehold.status} / ${minutes(firstHousehold.manual_minutes)}` : "等待项目数据"}</p>
              </div>
            </div>
            <button className="danger" type="button">
              <AlertTriangle size={16} /> 仅允许解决 issue，不允许强制发布
            </button>
          </div>
        </section>

        <section className="ops-grid">
          <div className="panel">
            <div className="panel-title">
              <h2>Support Tickets</h2>
              <span>{dashboard.supportTickets.length} open / pending</span>
            </div>
            <ListEmpty items={dashboard.supportTickets} empty="暂无 support ticket">
              {dashboard.supportTickets.slice(0, 6).map((ticket) => (
                <div className="list-row" key={ticket.ticket_id}>
                  <strong>{ticket.priority} · {ticket.category}</strong>
                  <span>{ticket.status} / owner {ticket.admin_owner_id || "未分配"}</span>
                </div>
              ))}
            </ListEmpty>
          </div>

          <div className="panel">
            <div className="panel-title">
              <h2>Stuck Projects</h2>
              <span>卡点 owner 推进</span>
            </div>
            <ListEmpty items={dashboard.stuckProjects} empty="暂无卡点项目">
              {dashboard.stuckProjects.slice(0, 6).map((project) => (
                <div className="list-row" key={project.project_id}>
                  <strong>{project.title}</strong>
                  <span>{project.ops_owner_id || "未分配"} / {project.stuck_reason || "未记录原因"}</span>
                </div>
              ))}
            </ListEmpty>
          </div>

          <div className="panel">
            <div className="panel-title">
              <h2>Cost / Manual Export</h2>
              <span>每户可导出</span>
            </div>
            <div className="gate-list">
              <Gate name="ai_cost_cents" value={String(totalAiCost)} tone="ok" />
              <Gate name="manual_intervention_count" value={String(manualInterventions)} tone="warn" />
              <Gate name="ops_owner_id coverage" value={ownerCoverage(dashboard.projects)} tone="warn" />
            </div>
          </div>

          <div className="panel">
            <div className="panel-title">
              <h2>Alerts</h2>
              <span>{dashboard.alerts.length} recent</span>
            </div>
            <ListEmpty items={dashboard.alerts} empty="暂无告警">
              {dashboard.alerts.slice(0, 5).map((alert) => (
                <div className="list-row" key={alert.alert_id}>
                  <strong>{alert.error_type}</strong>
                  <span>{alert.method} {alert.path}</span>
                </div>
              ))}
            </ListEmpty>
          </div>
        </section>
      </section>
    </main>
  );
}

async function loadAdminDashboard(): Promise<AdminDashboardData> {
  const configured = Boolean(process.env.ADMIN_API_TOKEN);
  if (!configured) {
    return emptyDashboard;
  }
  const client = new ChangjuanClient(adminApiBaseUrl(), process.env.ADMIN_API_TOKEN);
  const [metrics, projects, householdOps, supportTickets, stuckProjects, alerts] = await Promise.allSettled([
    client.pilotMetrics(),
    client.adminProjects(),
    client.householdOpsExport(),
    client.supportTickets(),
    client.stuckProjects(),
    client.alerts(),
  ]);

  return {
    metrics: resultOr(metrics, emptyMetrics),
    projects: resultOr(projects, []),
    householdOps: resultOr(householdOps, { households: [] }),
    supportTickets: resultOr(supportTickets, []),
    stuckProjects: resultOr(stuckProjects, []),
    alerts: resultOr(alerts, []),
    loadErrors: [metrics, projects, householdOps, supportTickets, stuckProjects, alerts].flatMap((result) =>
      result.status === "rejected" ? [String(result.reason)] : [],
    ),
    configured,
  };
}

function adminApiBaseUrl() {
  return process.env.ADMIN_API_BASE_URL || process.env.API_BASE_URL || "http://localhost:8000";
}

function resultOr<T>(result: PromiseSettledResult<T>, fallback: T): T {
  return result.status === "fulfilled" ? result.value : fallback;
}

function Metric({ icon, label, value, target }: { icon: React.ReactNode; label: string; value: string; target: string }) {
  return (
    <div className="metric">
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{target}</small>
    </div>
  );
}

function Gate({ name, value, tone }: { name: string; value: string; tone: "ok" | "warn" | "block" }) {
  return (
    <div className={`gate ${tone}`}>
      <span>{name}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ListEmpty<T>({ items, empty, children }: { items: T[]; empty: string; children: React.ReactNode }) {
  return items.length ? children : <div className="empty">{empty}</div>;
}

function percent(value: number) {
  return `${Math.round(value * 1000) / 10}%`;
}

function minutes(value: number | null) {
  return value == null ? "NA" : `${Math.round(value * 10) / 10} min`;
}

function shortId(id: string) {
  return id.slice(0, 8);
}

function paymentLabel(project: ProjectSummary) {
  return project.payment_status === "paid" ? `¥${project.payment_cents / 100}` : project.payment_status;
}

function ownerCoverage(projects: ProjectSummary[]) {
  if (!projects.length) return "0%";
  return percent(projects.filter((project) => project.ops_owner_id).length / projects.length);
}
