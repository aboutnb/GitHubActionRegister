import React, { useEffect, useState } from 'react';
import {
  ApiOutlined,
  ArrowUpOutlined,
  BarChartOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  MailOutlined,
  RiseOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { Card, Col, Empty, List, Row, Statistic, Tag } from 'antd';
import { fetchDashboardSummary } from '../services/api';
import { formatDateTime } from '../utils/datetime';

const stats = [
  {
    key: 'total_mail_accounts',
    label: '邮箱总量',
    helper: '库存邮箱资产',
    icon: <MailOutlined />,
    tone: 'blue',
  },
  {
    key: 'idle_mail_accounts',
    label: '可分配邮箱',
    helper: '可立即拉取',
    icon: <CheckCircleOutlined />,
    tone: 'green',
  },
  {
    key: 'used_mail_accounts',
    label: '已使用邮箱',
    helper: '已绑定或消耗',
    icon: <ClockCircleOutlined />,
    tone: 'amber',
  },
  {
    key: 'total_github_accounts',
    label: 'GitHub 总量',
    helper: '成品账号库存',
    icon: <DatabaseOutlined />,
    tone: 'violet',
  },
  {
    key: 'active_github_accounts',
    label: '可用 GitHub',
    helper: '可导出交付',
    icon: <CheckCircleOutlined />,
    tone: 'green',
  },
  {
    key: 'active_clients',
    label: '活跃客户端',
    helper: '在线执行器',
    icon: <ApiOutlined />,
    tone: 'cyan',
  },
];

const getNumber = (summary, key) => Number(summary[key] || 0);

function percent(value, total) {
  if (!total) return 0;
  return Math.round((value / total) * 100);
}

function StackedBar({ items }) {
  const total = items.reduce((sum, item) => sum + item.value, 0);

  return (
    <div className="stacked-metric">
      <div className="stacked-metric__bar" aria-hidden="true">
        {items.map((item) => (
          <span
            key={item.label}
            style={{
              width: `${percent(item.value, total)}%`,
              background: item.color,
            }}
          />
        ))}
      </div>
      <div className="stacked-metric__legend">
        {items.map((item) => (
          <div key={item.label}>
            <i style={{ background: item.color }} />
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function MiniAreaChart({ data, lines, yMax }) {
  const width = 420;
  const height = 180;
  const padding = 16;
  const innerWidth = width - padding * 2;
  const innerHeight = height - padding * 2;
  const maxValue = yMax || Math.max(...data.flatMap((item) => lines.map((line) => item[line.key])), 1);

  const getX = (index) => padding + (innerWidth * index) / Math.max(data.length - 1, 1);
  const getY = (value) => padding + innerHeight - (value / Math.max(maxValue, 1)) * innerHeight;

  const buildPath = (key) =>
    data
      .map((item, index) => `${index === 0 ? 'M' : 'L'} ${getX(index)} ${getY(item[key])}`)
      .join(' ');

  return (
    <div className="trend-chart">
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = padding + innerHeight * ratio;
          return <line key={ratio} x1={padding} y1={y} x2={width - padding} y2={y} className="trend-chart__grid" />;
        })}
        {lines.map((line) => (
          <path key={line.key} d={buildPath(line.key)} stroke={line.color} className="trend-chart__line" />
        ))}
        {lines.map((line) =>
          data.map((item, index) => (
            <circle
              key={`${line.key}-${item.date}`}
              cx={getX(index)}
              cy={getY(item[line.key])}
              r="3.5"
              fill={line.color}
              className="trend-chart__point"
            />
          )),
        )}
      </svg>
      <div className="trend-chart__footer">
        {data.map((item) => (
          <span key={item.date}>{item.date.slice(5)}</span>
        ))}
      </div>
    </div>
  );
}

function MiniBarChart({ data, bars, yMax }) {
  const maxValue = yMax || Math.max(...data.flatMap((item) => bars.map((bar) => item[bar.key])), 1);

  return (
    <div className="bar-chart">
      <div className="bar-chart__plot">
        {data.map((item) => (
          <div className="bar-chart__group" key={item.date}>
            <div className="bar-chart__bars">
              {bars.map((bar) => (
                <span
                  key={bar.key}
                  title={`${bar.label}: ${item[bar.key]}`}
                  style={{
                    height: `${(item[bar.key] / Math.max(maxValue, 1)) * 100}%`,
                    background: bar.color,
                  }}
                />
              ))}
            </div>
            <label>{item.date.slice(5)}</label>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [summary, setSummary] = useState({});

  useEffect(() => {
    fetchDashboardSummary().then(({ data }) => setSummary(data));
  }, []);

  const totalMail = getNumber(summary, 'total_mail_accounts');
  const idleMail = getNumber(summary, 'idle_mail_accounts');
  const registeredMail = getNumber(summary, 'registered_mail_accounts');
  const usedMail = getNumber(summary, 'used_mail_accounts');
  const totalGitHub = getNumber(summary, 'total_github_accounts');
  const activeGitHub = getNumber(summary, 'active_github_accounts');
  const totalClients = getNumber(summary, 'total_clients');
  const activeClients = getNumber(summary, 'active_clients');
  const otherMail = Math.max(totalMail - idleMail - registeredMail - usedMail, 0);
  const inactiveGitHub = Math.max(totalGitHub - activeGitHub, 0);
  const inactiveClients = Math.max(totalClients - activeClients, 0);
  const totalAssets = totalMail + totalGitHub + totalClients;
  const recentSyncLogs = summary.recent_sync_logs || [];
  const assetTrends = summary.asset_trends || [];
  const syncTrends = summary.sync_trends || [];
  const syncRequestTotal = syncTrends.reduce((sum, item) => sum + Number(item.sync_requests || 0), 0);
  const syncSuccessTotal = syncTrends.reduce((sum, item) => sum + Number(item.sync_success || 0), 0);
  const syncRunsTotal = syncTrends.reduce((sum, item) => sum + Number(item.sync_runs || 0), 0);
  const healthItems = [
    {
      title: '邮箱池',
      value: idleMail,
      total: totalMail,
      helper: `可分配 ${idleMail} · 已注册 ${registeredMail} · 已使用 ${usedMail} · 其他 ${otherMail}`,
      color: '#16a34a',
    },
    {
      title: 'GitHub 库存',
      value: activeGitHub,
      total: totalGitHub,
      helper: `可用 ${activeGitHub} · 不可用 ${inactiveGitHub}`,
      color: '#2563eb',
    },
    {
      title: '执行客户端',
      value: activeClients,
      total: totalClients,
      helper: `在线 ${activeClients} · 离线 ${inactiveClients}`,
      color: '#0891b2',
    },
  ];

  return (
    <div className="page-shell dashboard-page">
      <div className="dashboard-hero">
        <div>
          <span className="dashboard-hero__eyebrow">Asset Operations</span>
          <h2>仪表盘</h2>
          <p>集中查看邮箱资产、GitHub 成品账号和客户端同步状态。</p>
        </div>
        <div className="dashboard-hero__status">
          <SyncOutlined />
          <span>最近同步</span>
          <strong>{recentSyncLogs.length ? formatDateTime(recentSyncLogs[0].created_at) : '暂无记录'}</strong>
        </div>
      </div>
      <Row gutter={[16, 16]} className="metric-grid">
        {stats.map((item) => (
          <Col xs={24} sm={12} lg={8} xl={6} key={item.key}>
            <Card className={`stat-card stat-card--${item.tone}`}>
              <div className="stat-card__top">
                <span className="stat-card__icon">{item.icon}</span>
                <span>{item.helper}</span>
              </div>
              <Statistic title={item.label} value={summary[item.key] || 0} />
            </Card>
          </Col>
        ))}
      </Row>
      <Row gutter={[16, 16]} className="dashboard-chart-grid">
        <Col xs={24} xl={8}>
          <Card className="dashboard-panel" title="资产结构">
            <div className="dashboard-panel__summary">
              <strong>{totalAssets}</strong>
              <span>总资产对象</span>
            </div>
            <StackedBar
              items={[
                { label: '邮箱', value: totalMail, color: '#2563eb' },
                { label: 'GitHub', value: totalGitHub, color: '#16a34a' },
                { label: '客户端', value: totalClients, color: '#f59e0b' },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} xl={16}>
          <Card className="dashboard-panel" title="运行健康度">
            <div className="health-overview">
              {healthItems.map((item) => (
                <div className="health-item" key={item.title}>
                  <div className="health-item__top">
                    <div>
                      <h3>{item.title}</h3>
                      <p>{item.helper}</p>
                    </div>
                    <div className="health-item__metric">
                      <strong>{percent(item.value, item.total)}%</strong>
                      <span>{item.value}/{item.total || 0}</span>
                    </div>
                  </div>
                  <div className="health-item__bar" aria-hidden="true">
                    <span
                      style={{
                        width: `${percent(item.value, item.total)}%`,
                        background: item.color,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
            <div className="health-summary">
              <span>优先关注可分配邮箱与在线客户端，保障拉取和推送链路不断档。</span>
              <Tag color="blue">运营视图</Tag>
            </div>
          </Card>
        </Col>
      </Row>
      <Row gutter={[16, 16]} className="dashboard-chart-grid">
        <Col xs={24} xl={13}>
          <Card
            className="dashboard-panel"
            title="近 7 日资产新增趋势"
            extra={
              <span className="panel-extra">
                <RiseOutlined />
                实时按创建时间聚合
              </span>
            }
          >
            <div className="chart-panel">
              <div className="chart-panel__meta">
                <div>
                  <strong>{assetTrends.reduce((sum, item) => sum + Number(item.mail_created || 0), 0)}</strong>
                  <span>新增邮箱</span>
                </div>
                <div>
                  <strong>{assetTrends.reduce((sum, item) => sum + Number(item.github_created || 0), 0)}</strong>
                  <span>新增 GitHub</span>
                </div>
              </div>
              <MiniAreaChart
                data={assetTrends}
                lines={[
                  { key: 'mail_created', color: '#2563eb' },
                  { key: 'github_created', color: '#16a34a' },
                ]}
              />
              <div className="chart-legend">
                <span><i style={{ background: '#2563eb' }} />邮箱新增</span>
                <span><i style={{ background: '#16a34a' }} />GitHub 新增</span>
              </div>
            </div>
          </Card>
        </Col>
        <Col xs={24} xl={11}>
          <Card
            className="dashboard-panel"
            title="近 7 日同步吞吐"
            extra={
              <span className="panel-extra">
                <BarChartOutlined />
                请求量与成功量
              </span>
            }
          >
            <div className="chart-panel">
              <div className="chart-panel__meta">
                <div>
                  <strong>{syncRequestTotal}</strong>
                  <span>总请求量</span>
                </div>
                <div>
                  <strong>{syncSuccessTotal}</strong>
                  <span>成功条数</span>
                </div>
                <div>
                  <strong>{syncRunsTotal}</strong>
                  <span>执行次数</span>
                </div>
              </div>
              <MiniBarChart
                data={syncTrends}
                bars={[
                  { key: 'sync_requests', label: '请求量', color: '#60a5fa' },
                  { key: 'sync_success', label: '成功量', color: '#22c55e' },
                ]}
              />
              <div className="chart-summary">
                <span>
                  <ArrowUpOutlined />
                  当前成功率 {syncRequestTotal ? Math.round((syncSuccessTotal / syncRequestTotal) * 100) : 0}%
                </span>
              </div>
            </div>
          </Card>
        </Col>
      </Row>
      <Row gutter={[16, 16]} className="activity-grid">
        <Col xs={24} xl={8}>
          <Card className="activity-card" title="最近批次">
            <List
              dataSource={summary.recent_batches || []}
              locale={{ emptyText: '暂无批次' }}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <>
                        <Tag>{item.batch_type}</Tag>
                        {item.batch_no}
                      </>
                    }
                    description={`${item.source} · ${formatDateTime(item.created_at)}`}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card className="activity-card" title="最近审计">
            <List
              dataSource={summary.recent_audits || []}
              locale={{ emptyText: '暂无审计记录' }}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={item.action}
                    description={`${item.target_type} #${item.target_id || '-'} · ${formatDateTime(
                      item.created_at,
                    )}`}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card className="activity-card" title="最近同步">
            {recentSyncLogs.length ? (
              <div className="sync-timeline">
                {recentSyncLogs.map((item, index) => (
                  <div className="sync-timeline__item" key={`${item.action}-${item.created_at}-${index}`}>
                    <span className="sync-timeline__dot" />
                    <div>
                      <Tag>{item.action}</Tag>
                      <p>{item.message || '-'}</p>
                      <time>{formatDateTime(item.created_at)}</time>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无同步记录" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
