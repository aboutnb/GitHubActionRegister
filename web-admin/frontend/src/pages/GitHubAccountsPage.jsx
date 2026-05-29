import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import {
  bulkDeleteGitHubAccounts,
  bulkExportGitHubAccounts,
  bulkUpdateGitHubStatus,
  createGitHubAccount,
  deleteGitHubAccount,
  exportGitHubAccounts,
  fetchGitHubAccounts,
  fetchGitHubHealthCheckConfig,
  importGitHubAccounts,
  runGitHubHealthCheck,
  updateGitHubAccount,
  updateGitHubHealthCheckConfig,
} from '../services/api';
import SensitiveValue from '../components/SensitiveValue';
import { usePersistentState } from '../hooks/usePersistentState';
import { formatDateTime } from '../utils/datetime';

const statusColor = {
  active: 'green',
  disabled: 'default',
  sold: 'purple',
  locked: 'red',
  unknown: 'gold',
};

const statusOptions = [
  { label: '可用', value: 'active' },
  { label: '禁用', value: 'disabled' },
  { label: '已售', value: 'sold' },
  { label: '锁定', value: 'locked' },
  { label: '未知', value: 'unknown' },
];

const healthStatusColor = {
  alive: 'green',
  not_found: 'default',
  error: 'red',
  unknown: 'gold',
  skipped: 'cyan',
};

const healthStatusLabel = {
  alive: '存活',
  not_found: '404',
  error: '异常',
  unknown: '未测活',
  skipped: '跳过',
};

const healthStatusOptions = [
  { label: '存活', value: 'alive' },
  { label: '404/未找到', value: 'not_found' },
  { label: '异常', value: 'error' },
  { label: '未测活', value: 'unknown' },
];

const cronPresetOptions = [
  { label: '每半个月（1号/15号 00:00）', value: '0 0 1,15 * *' },
  { label: '每月 1 号 00:00', value: '0 0 1 * *' },
  { label: '每月 15 号 00:00', value: '0 0 15 * *' },
  { label: '自定义', value: 'custom' },
];

function resolveCronPreset(cronExpression) {
  const value = String(cronExpression || '').trim();
  return cronPresetOptions.some((option) => option.value === value) ? value : 'custom';
}

function deriveGitHubUsername(email) {
  const value = String(email || '').trim();
  if (!value) return '';
  return value.includes('@') ? value.split('@')[0].trim() : value;
}

function parseGitHubImportLine(line) {
  const raw = String(line || '').trim();
  if (!raw) return null;
  const parts = raw.split('---').map((item) => item.trim());
  if (parts.length !== 3 || !parts[0] || !parts[1]) {
    throw new Error('导入格式应为：邮箱---密码---2FA密钥/NO_2FA');
  }
  return {
    email: parts[0],
    github_username: deriveGitHubUsername(parts[0]),
    github_password: parts[1],
    totp_secret: parts[2] || 'NO_2FA',
    raw_line: raw,
  };
}

function parseProxyPoolText(value) {
  return String(value || '')
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export default function GitHubAccountsPage() {
  const [filters, setFilters] = usePersistentState('github_accounts_filters', {
    query: '',
    statusFilter: undefined,
    healthStatusFilter: undefined,
    twoFaFilter: undefined,
    ageBucket: undefined,
    sortBy: undefined,
    sortOrder: undefined,
  });
  const [rows, setRows] = useState([]);
  const [exportRows, setExportRows] = useState([]);
  const [exportMeta, setExportMeta] = useState(null);
  const [importOpen, setImportOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [healthConfigOpen, setHealthConfigOpen] = useState(false);
  const [healthConfigMeta, setHealthConfigMeta] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailRow, setDetailRow] = useState(null);
  const [editingRow, setEditingRow] = useState(null);
  const [loading, setLoading] = useState(false);
  const [healthRunning, setHealthRunning] = useState(false);
  const [healthConfigLoading, setHealthConfigLoading] = useState(false);
  const [healthConfigSaving, setHealthConfigSaving] = useState(false);
  const [cronMode, setCronMode] = useState('0 0 1,15 * *');
  const query = filters.query;
  const statusFilter = filters.statusFilter;
  const healthStatusFilter = filters.healthStatusFilter;
  const twoFaFilter = filters.twoFaFilter;
  const ageBucket = filters.ageBucket;
  const sortBy = filters.sortBy;
  const sortOrder = filters.sortOrder;
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [form] = Form.useForm();
  const [importForm] = Form.useForm();
  const [healthForm] = Form.useForm();
  const selectedCount = selectedRowKeys.length;

  const loadData = async (
    page = pagination.current,
    pageSize = pagination.pageSize,
    nextQuery = query,
    nextStatus = statusFilter,
    nextHealthStatus = healthStatusFilter,
    nextTwoFa = twoFaFilter,
    nextAgeBucket = ageBucket,
    nextSortBy = sortBy,
    nextSortOrder = sortOrder,
  ) => {
    const { data } = await fetchGitHubAccounts({
      page,
      page_size: pageSize,
      q: nextQuery || undefined,
      status: nextStatus || undefined,
      health_status: nextHealthStatus || undefined,
      two_fa_enabled: nextTwoFa,
      age_bucket: nextAgeBucket || undefined,
      sort_by: nextSortBy || undefined,
      sort_order: nextSortOrder || undefined,
    });
    setRows(data.items);
    setPagination({ current: data.page, pageSize: data.page_size, total: data.total });
  };

  useEffect(() => {
    loadData(1, pagination.pageSize, query, statusFilter, healthStatusFilter, twoFaFilter, ageBucket, sortBy, sortOrder);
  }, [query, statusFilter, healthStatusFilter, twoFaFilter, ageBucket, sortBy, sortOrder]);

  const openCreate = () => {
    setEditingRow(null);
    form.resetFields();
    form.setFieldsValue({ status: 'active', two_fa_enabled: true });
    setEditorOpen(true);
  };

  const openEdit = (row) => {
    setEditingRow(row);
    form.setFieldsValue({
      email: row.email,
      github_username: row.github_username,
      status: row.status,
      two_fa_enabled: row.two_fa_enabled,
      remark: row.remark,
      github_password: '',
      totp_secret: '',
      recovery_codes_text: (row.recovery_codes || []).join('\n'),
    });
    setEditorOpen(true);
  };

  const openDetail = (row) => {
    setDetailRow(row);
    setDetailOpen(true);
  };

  const handleExport = async () => {
    try {
      const { data } = await exportGitHubAccounts();
      setExportRows(data.items || []);
      setExportMeta({
        batchNo: data.batch_no,
        totalCount: data.total_count,
        successCount: data.success_count,
      });
      message.success(`导出了 ${data.success_count} 条账号`);
    } catch (error) {
      message.error(error?.response?.data?.detail || '导出失败');
    }
  };

  const handleImport = async (values) => {
    setLoading(true);
    try {
      const items = values.lines
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .map(parseGitHubImportLine);
      const { data } = await importGitHubAccounts({ items });
      message.success(`导入完成：${data.success_count} 条，重复 ${data.duplicate_count} 条`);
      setImportOpen(false);
      importForm.resetFields();
      loadData();
    } catch (error) {
      message.error(error?.response?.data?.detail || error?.message || '导入失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (values) => {
    setLoading(true);
    try {
      const payload = {
        ...values,
        recovery_codes: values.recovery_codes_text
          ? values.recovery_codes_text
              .split('\n')
              .map((item) => item.trim())
              .filter(Boolean)
          : [],
      };
      delete payload.recovery_codes_text;
      if (editingRow) {
        await updateGitHubAccount(editingRow.id, payload);
        message.success('GitHub 账号已更新');
      } else {
        await createGitHubAccount(payload);
        message.success('GitHub 账号已创建');
      }
      setEditorOpen(false);
      form.resetFields();
      loadData();
    } catch (error) {
      message.error(error?.response?.data?.detail || '保存失败');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (row) => {
    try {
      await deleteGitHubAccount(row.id);
      message.success('GitHub 账号已删除');
      loadData();
    } catch (error) {
      message.error(error?.response?.data?.detail || '删除失败');
    }
  };

  const handleBulkStatus = async (status) => {
    if (!selectedRowKeys.length) {
      message.warning('请先选择 GitHub 账号');
      return;
    }
    await bulkUpdateGitHubStatus({ ids: selectedRowKeys, status });
    message.success('批量状态更新完成');
    setSelectedRowKeys([]);
    loadData();
  };

  const handleBulkDelete = async () => {
    if (!selectedRowKeys.length) {
      message.warning('请先选择 GitHub 账号');
      return;
    }
    const { data } = await bulkDeleteGitHubAccounts({ ids: selectedRowKeys });
    message.success(`已删除 ${data.deleted} 条 GitHub 账号`);
    setSelectedRowKeys([]);
    loadData();
  };

  const handleBulkExport = async () => {
    if (!selectedRowKeys.length) {
      message.warning('请先选择 GitHub 账号');
      return;
    }
    const { data } = await bulkExportGitHubAccounts({ ids: selectedRowKeys });
    setExportRows(data.items || []);
    setExportMeta({
      batchNo: data.batch_no,
      totalCount: data.total_count,
      successCount: data.success_count,
    });
    message.success(`已导出 ${data.success_count} 条选中账号`);
  };

  const openHealthConfig = async () => {
    setHealthConfigOpen(true);
    setHealthConfigLoading(true);
    try {
      const { data } = await fetchGitHubHealthCheckConfig();
      const cronExpression = data.cron_expression || '0 0 1,15 * *';
      const preset = resolveCronPreset(cronExpression);
      setHealthConfigMeta(data);
      setCronMode(preset);
      healthForm.setFieldsValue({
        enabled: data.enabled,
        cron_preset: preset,
        cron_expression: cronExpression,
        accounts_per_proxy: data.accounts_per_proxy || 15,
        timeout_seconds: data.timeout_seconds || 10,
        proxy_urls_text: (data.proxy_urls || []).join('\n'),
      });
    } catch (error) {
      message.error(error?.response?.data?.detail || '读取测活配置失败');
    } finally {
      setHealthConfigLoading(false);
    }
  };

  const handleSaveHealthConfig = async (values) => {
    setHealthConfigSaving(true);
    try {
      const cronExpression = values.cron_preset === 'custom' ? values.cron_expression : values.cron_preset;
      const { data } = await updateGitHubHealthCheckConfig({
        enabled: Boolean(values.enabled),
        cron_expression: cronExpression,
        proxy_urls: parseProxyPoolText(values.proxy_urls_text),
        accounts_per_proxy: values.accounts_per_proxy,
        timeout_seconds: values.timeout_seconds,
      });
      setHealthConfigMeta(data);
      message.success(data.enabled ? '测活定时任务已启用' : '测活配置已保存');
      setHealthConfigOpen(false);
    } catch (error) {
      message.error(error?.response?.data?.detail || '保存测活配置失败');
    } finally {
      setHealthConfigSaving(false);
    }
  };

  const handleRunHealthCheck = async (accountIds) => {
    if (healthRunning) return;
    if (accountIds && !accountIds.length) {
      message.warning('请先选择 GitHub 账号');
      return;
    }
    setHealthRunning(true);
    try {
      const { data } = await runGitHubHealthCheck({
        account_ids: accountIds?.length ? accountIds : undefined,
        use_saved_config: true,
      });
      const skippedText = data.skipped_count ? `，跳过 ${data.skipped_count} 条（代理池容量不足）` : '';
      message.success(
        `测活完成：已测 ${data.checked_count} 条，存活 ${data.alive_count} 条，404 ${data.not_found_count} 条，异常 ${data.error_count} 条${skippedText}`,
      );
      loadData(
        pagination.current,
        pagination.pageSize,
        query,
        statusFilter,
        healthStatusFilter,
        twoFaFilter,
        ageBucket,
        sortBy,
        sortOrder,
      );
    } catch (error) {
      message.error(error?.response?.data?.detail || '账号测活失败');
    } finally {
      setHealthRunning(false);
    }
  };

  const resetFilters = () => {
    setFilters({
      query: '',
      statusFilter: undefined,
      healthStatusFilter: undefined,
      twoFaFilter: undefined,
      ageBucket: undefined,
      sortBy: undefined,
      sortOrder: undefined,
    });
  };

  const clearSelection = () => {
    setSelectedRowKeys([]);
  };

  const buildExportLine = (row) => [
    row.email || '',
    row.github_password || '',
    row.totp_secret || 'NO_2FA',
  ].join('---');

  const handleCopyExportRow = async (row) => {
    await navigator.clipboard.writeText(buildExportLine(row));
    message.success('已复制当前导出行');
  };

  const handleCopyExportAll = async () => {
    const text = exportRows.map(buildExportLine).join('\n');
    await navigator.clipboard.writeText(text);
    message.success(`已复制 ${exportRows.length} 条导出结果`);
  };

  const handleDownloadExport = () => {
    const text = exportRows.map(buildExportLine).join('\n');
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${exportMeta?.batchNo || 'github-accounts'}.txt`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const handleTableChange = (nextPagination, _tableFilters, sorter) => {
    const sorterValue = Array.isArray(sorter) ? sorter[0] : sorter;
    const nextSortBy = sorterValue?.order ? sorterValue.field : undefined;
    const nextSortOrder = sorterValue?.order || undefined;
    setFilters((prev) => ({
      ...prev,
      sortBy: nextSortBy,
      sortOrder: nextSortOrder,
    }));
    loadData(
      nextPagination.current,
      nextPagination.pageSize,
      query,
      statusFilter,
      healthStatusFilter,
      twoFaFilter,
      ageBucket,
      nextSortBy,
      nextSortOrder,
    );
  };

  const columns = useMemo(
    () => [
      {
        title: '用户名',
        dataIndex: 'github_username',
        width: 180,
        ellipsis: true,
        sorter: true,
        sortOrder: sortBy === 'github_username' ? sortOrder : null,
        render: (value) => value || '-',
      },
      {
        title: '邮箱',
        dataIndex: 'email',
        width: 240,
        ellipsis: true,
        sorter: true,
        sortOrder: sortBy === 'email' ? sortOrder : null,
        render: (value) => value || '-',
      },
      {
        title: '2FA',
        dataIndex: 'two_fa_enabled',
        width: 110,
        sorter: true,
        sortOrder: sortBy === 'two_fa_enabled' ? sortOrder : null,
        render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? '已启用' : '未启用'}</Tag>,
      },
      {
        title: '状态',
        dataIndex: 'status',
        width: 110,
        sorter: true,
        sortOrder: sortBy === 'status' ? sortOrder : null,
        render: (value) => <Tag color={statusColor[value] || 'default'}>{value}</Tag>,
      },
      {
        title: '测活',
        dataIndex: 'health_status',
        width: 120,
        sorter: true,
        sortOrder: sortBy === 'health_status' ? sortOrder : null,
        render: (value, row) => (
          <Tooltip
            title={
              row.health_error
                ? `HTTP ${row.health_http_status || '-'} · ${row.health_error}`
                : row.health_http_status
                  ? `HTTP ${row.health_http_status}`
                  : '尚未测活'
            }
          >
            <Tag color={healthStatusColor[value] || 'default'}>{healthStatusLabel[value] || value || '-'}</Tag>
          </Tooltip>
        ),
      },
      {
        title: '最近测活',
        dataIndex: 'health_checked_at',
        width: 170,
        sorter: true,
        sortOrder: sortBy === 'health_checked_at' ? sortOrder : null,
        render: (value) => value || '-',
      },
      {
        title: '密码',
        key: 'github_password',
        width: 180,
        render: (_, row) => (
          <SensitiveValue value={row.github_password} tooltip="悬浮显示密码，点击复制" />
        ),
      },
      {
        title: '2FA 密钥',
        key: 'totp_secret',
        width: 180,
        render: (_, row) => (
          <SensitiveValue value={row.totp_secret} tooltip="悬浮显示 2FA 密钥，点击复制" />
        ),
      },
      {
        title: '来源客户端',
        dataIndex: 'source_client_name',
        width: 180,
        ellipsis: true,
        sorter: true,
        sortOrder: sortBy === 'source_client_name' ? sortOrder : null,
        render: (value) => value || '-',
      },
      { title: '创建时间', dataIndex: 'created_at', width: 170, sorter: true, sortOrder: sortBy === 'created_at' ? sortOrder : null, render: formatDateTime },
      { title: '更新时间', dataIndex: 'updated_at', width: 170, sorter: true, sortOrder: sortBy === 'updated_at' ? sortOrder : null, render: formatDateTime },
      { title: '最近导出', dataIndex: 'last_exported_at', width: 170, sorter: true, sortOrder: sortBy === 'last_exported_at' ? sortOrder : null, render: (value) => value ? formatDateTime(value) : '-' },
      { title: '备注', dataIndex: 'remark', width: 220, ellipsis: true, render: (value) => value || '-' },
      {
        title: '操作',
        key: 'actions',
        width: 220,
        fixed: 'right',
        align: 'right',
        className: 'actions-column',
        render: (_, row) => (
          <Space className="table-action-bar">
            <Button type="link" onClick={() => openDetail(row)}>
              详情
            </Button>
            <Button type="link" onClick={() => handleRunHealthCheck([row.id])} loading={healthRunning}>
              测活
            </Button>
            <Button type="link" onClick={() => openEdit(row)}>
              编辑
            </Button>
            <Popconfirm title="确认删除这个 GitHub 账号吗？" onConfirm={() => handleDelete(row)}>
              <Button type="link" danger>
                删除
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [
      query,
      statusFilter,
      healthStatusFilter,
      twoFaFilter,
      ageBucket,
      pagination.current,
      pagination.pageSize,
      sortBy,
      sortOrder,
      healthRunning,
    ],
  );

  const exportColumns = useMemo(
    () => [
      {
        title: '导出格式预览',
        key: 'export_line',
        width: 440,
        render: (_, row) => (
          <Typography.Text copyable={{ text: buildExportLine(row) }}>
            {buildExportLine(row)}
          </Typography.Text>
        ),
      },
      {
        title: 'GitHub 密码',
        dataIndex: 'github_password',
        width: 180,
        render: (value) => (
          <SensitiveValue value={value} tooltip="悬浮显示 GitHub 密码，点击复制" />
        ),
      },
      {
        title: '2FA 密钥',
        dataIndex: 'totp_secret',
        width: 180,
        render: (value) => (
          <SensitiveValue value={value} tooltip="悬浮显示 2FA 密钥，点击复制" />
        ),
      },
      {
        title: '复制',
        key: 'copy',
        width: 96,
        fixed: 'right',
        align: 'right',
        className: 'actions-column',
        render: (_, row) => (
          <Button className="table-action-bar__single" type="link" size="small" onClick={() => handleCopyExportRow(row)}>
            复制本行
          </Button>
        ),
      },
    ],
    [],
  );

  return (
    <div className="page-shell">
      <div className="page-header">
        <h2>GitHub 账号库</h2>
        <p>支持完整 GitHub 成品账号的增删改查，凭证仅在保存和导出时处理。</p>
      </div>
      <Card
        className="table-card"
        extra={
          <div className="table-toolbar-stack">
            <Space className="table-toolbar" wrap>
              <Input.Search
                allowClear
                placeholder="搜索邮箱 / 用户名 / 备注"
                style={{ width: 300 }}
                value={query}
                onChange={(event) =>
                  setFilters((prev) => ({ ...prev, query: event.target.value }))
                }
                onSearch={(value) => setFilters((prev) => ({ ...prev, query: value }))}
              />
              <Select
                allowClear
                placeholder="状态筛选"
                style={{ width: 150 }}
                options={statusOptions}
                value={statusFilter}
                onChange={(value) => setFilters((prev) => ({ ...prev, statusFilter: value }))}
              />
              <Select
                allowClear
                placeholder="测活状态"
                style={{ width: 150 }}
                options={healthStatusOptions}
                value={healthStatusFilter}
                onChange={(value) => setFilters((prev) => ({ ...prev, healthStatusFilter: value }))}
              />
              <Select
                allowClear
                placeholder="2FA 筛选"
                style={{ width: 140 }}
                options={[
                  { label: '已启用 2FA', value: true },
                  { label: '未启用 2FA', value: false },
                ]}
                value={twoFaFilter}
                onChange={(value) => setFilters((prev) => ({ ...prev, twoFaFilter: value }))}
              />
              <Select
                allowClear
                placeholder="时间段筛选"
                style={{ width: 140 }}
                options={[
                  { label: '新号', value: 'new' },
                  { label: '7D+', value: '7d_plus' },
                  { label: '30D+', value: '30d_plus' },
                ]}
                value={ageBucket}
                onChange={(value) => setFilters((prev) => ({ ...prev, ageBucket: value }))}
              />
              <Button onClick={resetFilters}>重置筛选</Button>
              <Button onClick={openHealthConfig} loading={healthConfigLoading}>
                测活配置
              </Button>
              <Button onClick={() => handleRunHealthCheck()} loading={healthRunning}>
                测活全部
              </Button>
              <Button onClick={() => setImportOpen(true)}>批量导入</Button>
              <Button onClick={handleExport}>导出可用账号</Button>
              <Button type="primary" onClick={openCreate}>
                新增 GitHub 账号
              </Button>
            </Space>
            {healthConfigMeta ? (
              <div className="table-toolbar__meta">
                <Typography.Text type="secondary">
                  测活定时：{healthConfigMeta.enabled ? '已启用' : '已关闭'} · {healthConfigMeta.cron_expression}
                  {' · '}
                  每个代理 {healthConfigMeta.accounts_per_proxy} 条 · 超时 {healthConfigMeta.timeout_seconds}s
                </Typography.Text>
              </div>
            ) : null}
          </div>
        }
      >
        {selectedCount > 0 && (
          <div className="selection-toolbar">
            <Space size={12}>
              <span className="selection-toolbar__count">已选 {selectedCount} 条 GitHub 账号</span>
              <Button size="small" onClick={() => handleRunHealthCheck(selectedRowKeys)} loading={healthRunning}>
                测活选中
              </Button>
              <Popconfirm
                title={`确认将选中的 ${selectedCount} 条 GitHub 账号标记为可用吗？`}
                description="状态会更新为 active。"
                onConfirm={() => handleBulkStatus('active')}
                okText="确认更新"
                cancelText="取消"
              >
                <Button size="small">恢复可用</Button>
              </Popconfirm>
              <Popconfirm
                title={`确认将选中的 ${selectedCount} 条 GitHub 账号标记为已售吗？`}
                description="状态会更新为 sold。"
                onConfirm={() => handleBulkStatus('sold')}
                okText="确认标记"
                cancelText="取消"
              >
                <Button size="small">标记已售</Button>
              </Popconfirm>
              <Popconfirm
                title={`确认将选中的 ${selectedCount} 条 GitHub 账号批量禁用吗？`}
                description="状态会更新为 disabled，账号仍会保留在库中。"
                onConfirm={() => handleBulkStatus('disabled')}
                okText="确认禁用"
                cancelText="取消"
              >
                <Button size="small">批量禁用</Button>
              </Popconfirm>
              <Popconfirm
                title={`确认导出选中的 ${selectedCount} 条 GitHub 账号吗？`}
                description="导出结果会显示在当前页面下方的预览表格中。"
                onConfirm={handleBulkExport}
                okText="确认导出"
                cancelText="取消"
              >
                <Button size="small">批量导出</Button>
              </Popconfirm>
              <Popconfirm
                title={`确认批量删除选中的 ${selectedCount} 条 GitHub 账号吗？`}
                description="删除后账号凭证和导出记录关联会一并清除。"
                onConfirm={handleBulkDelete}
                okText="确认删除"
                cancelText="取消"
              >
                <Button size="small" danger>
                  批量删除
                </Button>
              </Popconfirm>
              <Button size="small" onClick={clearSelection}>
                取消选择
              </Button>
            </Space>
          </div>
        )}
        <Table
          className="management-table"
          size="middle"
          rowKey="id"
          dataSource={rows}
          scroll={{ x: 1940 }}
          sticky
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys,
          }}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
            onChange: (page, pageSize) => loadData(page, pageSize),
          }}
          onChange={handleTableChange}
          columns={columns}
        />
      </Card>
      {exportRows.length > 0 && (
        <Card
          className="table-card"
          style={{ marginTop: 16 }}
          title="最近一次导出预览"
          extra={
            <Space size={12}>
              <Typography.Text type="secondary">
                {exportMeta?.batchNo ? `批次 ${exportMeta.batchNo} · ` : ''}
                共 {exportRows.length} 条
              </Typography.Text>
              <Button size="small" onClick={handleCopyExportAll}>
                复制全部（邮箱---密码---2FA）
              </Button>
              <Button size="small" onClick={handleDownloadExport}>
                下载 TXT
              </Button>
              <Button
                size="small"
                onClick={() => {
                  setExportRows([]);
                  setExportMeta(null);
                }}
              >
                清空预览
              </Button>
            </Space>
          }
        >
          <Table
            className="management-table"
            rowKey={(row) => `${row.email}-${row.github_username || 'no-user'}`}
            size="small"
            pagination={false}
            scroll={{ x: 1240 }}
            sticky
            dataSource={exportRows}
            columns={exportColumns}
          />
        </Card>
      )}

      <Drawer
        title="GitHub 账号测活配置"
        width={560}
        open={healthConfigOpen}
        onClose={() => setHealthConfigOpen(false)}
        destroyOnClose
      >
        <div className="health-config-panel">
          <Alert
            type="info"
            showIcon
            message="测活规则"
            description="调用 GitHub users/{用户名} API：正常返回用户 JSON 且包含 login 记为存活；404 记为未找到；其他网络或 HTTP 异常记为异常。代理池按顺序分配，每个代理本轮最多测 1-20 个账号。"
          />
          {healthConfigMeta ? (
            <div className="health-config-summary">
              <span>上次运行：{healthConfigMeta.last_run_at || '-'}</span>
              <span>下次运行：{healthConfigMeta.next_run_at || '-'}</span>
              <span>最近批次：{healthConfigMeta.last_batch_no || '-'}</span>
            </div>
          ) : null}
          <Form
            layout="vertical"
            form={healthForm}
            onFinish={handleSaveHealthConfig}
            disabled={healthConfigLoading}
          >
            <Form.Item label="启用定时测活" name="enabled" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item
              label="测活频率"
              name="cron_preset"
              rules={[{ required: true, message: '请选择测活频率' }]}
                extra="为避免浪费代理资源，定时测活只允许半个月或更低频率。需要固定日期时可选择“自定义”。"
            >
              <Select
                options={cronPresetOptions}
                onChange={(value) => {
                  setCronMode(value);
                  if (value !== 'custom') {
                    healthForm.setFieldsValue({ cron_expression: value });
                  }
                }}
              />
            </Form.Item>
            {cronMode === 'custom' ? (
              <Form.Item
                label="自定义 cron 表达式"
                name="cron_expression"
                rules={[{ required: true, message: '请输入 5 段 cron 表达式' }]}
                extra="按服务端本地时间执行，间隔不能小于半个月。示例：0 0 1 * * 表示每月 1 号 00:00。"
              >
                <Input placeholder="0 0 1 * *" />
              </Form.Item>
            ) : (
              <Form.Item
                label="cron 表达式"
                name="cron_expression"
                extra="系统会把选择的频率保存为标准 5 段 cron 表达式。"
              >
                <Input disabled />
              </Form.Item>
            )}
            <Form.Item
              label="每个代理最多测活账号数"
              name="accounts_per_proxy"
              rules={[{ required: true, message: '请输入每个代理的账号数' }]}
              extra="建议 15-20，后端会限制在 1-20。代理池容量不足时，剩余账号本轮跳过。"
            >
              <InputNumber min={1} max={20} style={{ width: 180 }} />
            </Form.Item>
            <Form.Item
              label="请求超时（秒）"
              name="timeout_seconds"
              rules={[{ required: true, message: '请输入请求超时时间' }]}
            >
              <InputNumber min={2} max={60} style={{ width: 180 }} />
            </Form.Item>
            <Form.Item
              label="代理池"
              name="proxy_urls_text"
              extra="每行一个代理，支持 ip:port、user:pass@ip:port 或完整 http/socks URL；留空则直连 GitHub。"
            >
              <Input.TextArea rows={8} placeholder={`127.0.0.1:7890\nhttp://user:pass@1.2.3.4:8000`} />
            </Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={healthConfigSaving}>
                保存配置
              </Button>
              <Button onClick={() => setHealthConfigOpen(false)}>取消</Button>
            </Space>
          </Form>
        </div>
      </Drawer>

      <Drawer
        title="批量导入 GitHub 账号"
        width={520}
        open={importOpen}
        onClose={() => setImportOpen(false)}
        destroyOnClose
      >
        <Form layout="vertical" form={importForm} onFinish={handleImport}>
          <Form.Item
            label="多行导入内容"
            name="lines"
            rules={[{ required: true, message: '请输入多行导入内容' }]}
            extra="每行一条，格式：邮箱---密码---2FA密钥。未开启 2FA 的账号请填写 NO_2FA。用户名会自动取邮箱 @ 前缀。"
          >
            <Input.TextArea
              rows={14}
              placeholder={`JeanPainter961956@outlook.com---MZVcd673@Git2026---3KFJPTQ2WSZAOUP6\nWilliamWatson148@outlook.com---TLFovyw60@Git2026---NO_2FA`}
            />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={loading}>
              开始导入
            </Button>
            <Button onClick={() => setImportOpen(false)}>取消</Button>
          </Space>
        </Form>
      </Drawer>

      <Modal
        title={editingRow ? '编辑 GitHub 账号' : '新增 GitHub 账号'}
        open={editorOpen}
        onCancel={() => setEditorOpen(false)}
        footer={null}
        width={560}
        destroyOnClose
      >
        <Form layout="vertical" form={form} onFinish={handleSave}>
          <Form.Item
            label="邮箱"
            name="email"
            rules={[{ required: true, message: '请输入邮箱' }]}
          >
            <Input placeholder="例如：JeanPainter961956@outlook.com" />
          </Form.Item>
          <Form.Item label="用户名" name="github_username">
            <Input placeholder="留空时自动取邮箱 @ 前缀" />
          </Form.Item>
          <Form.Item
            label={editingRow ? '新密码' : '密码'}
            name="github_password"
            rules={editingRow ? [] : [{ required: true, message: '请输入密码' }]}
          >
            <Input.Password placeholder={editingRow ? '留空则保持不变' : '请输入密码'} />
          </Form.Item>
          <Form.Item
            label={editingRow ? '新 2FA 密钥' : '2FA 密钥'}
            name="totp_secret"
            rules={editingRow ? [] : [{ required: true, message: '请输入 2FA 密钥' }]}
          >
            <Input placeholder={editingRow ? '留空则保持不变' : '请输入 2FA 密钥'} />
          </Form.Item>
          <Form.Item label="Recovery Codes（非必填）" name="recovery_codes_text">
            <Input.TextArea
              rows={4}
              placeholder="每行一个 code，留空即可"
            />
          </Form.Item>
          <Form.Item label="状态" name="status" rules={[{ required: true, message: '请选择状态' }]}>
            <Select options={statusOptions} />
          </Form.Item>
          <Form.Item label="2FA 启用" name="two_fa_enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item label="备注" name="remark">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={loading}>
              保存
            </Button>
            <Button onClick={() => setEditorOpen(false)}>取消</Button>
          </Space>
        </Form>
      </Modal>

      <Drawer
        title="GitHub 账号详情"
        width={560}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        destroyOnClose
      >
        {detailRow ? (
          <div className="detail-panel">
            <div className="detail-panel__item">
              <div className="detail-panel__label">邮箱</div>
              <div className="detail-panel__value">{detailRow.email}</div>
            </div>
            <div className="detail-panel__item">
              <div className="detail-panel__label">用户名</div>
              <div className="detail-panel__value">{detailRow.github_username || '-'}</div>
            </div>
            <div className="detail-panel__item">
              <div className="detail-panel__label">密码</div>
              <div className="detail-panel__value">
                <SensitiveValue value={detailRow.github_password} tooltip="悬浮显示密码，点击复制" />
              </div>
            </div>
            <div className="detail-panel__item">
              <div className="detail-panel__label">来源客户端</div>
              <div className="detail-panel__value">{detailRow.source_client_name || '-'}</div>
            </div>
            <div className="detail-panel__item">
              <div className="detail-panel__label">状态</div>
              <div className="detail-panel__value">{detailRow.status || '-'}</div>
            </div>
            <div className="detail-panel__item">
              <div className="detail-panel__label">测活状态</div>
              <div className="detail-panel__value">
                <Tag color={healthStatusColor[detailRow.health_status] || 'default'}>
                  {healthStatusLabel[detailRow.health_status] || detailRow.health_status || '-'}
                </Tag>
              </div>
            </div>
            <div className="detail-panel__item">
              <div className="detail-panel__label">最近测活</div>
              <div className="detail-panel__value">{detailRow.health_checked_at || '-'}</div>
            </div>
            <div className="detail-panel__item detail-panel__item--full">
              <div className="detail-panel__label">测活错误</div>
              <div className="detail-panel__value">
                {detailRow.health_error
                  ? `HTTP ${detailRow.health_http_status || '-'} · ${detailRow.health_error}`
                  : detailRow.health_http_status
                    ? `HTTP ${detailRow.health_http_status}`
                    : '-'}
              </div>
            </div>
            <div className="detail-panel__item">
              <div className="detail-panel__label">2FA</div>
              <div className="detail-panel__value">{detailRow.two_fa_enabled ? '已启用' : '未启用'}</div>
            </div>
            <div className="detail-panel__item">
              <div className="detail-panel__label">2FA 密钥</div>
              <div className="detail-panel__value">
                <SensitiveValue value={detailRow.totp_secret} tooltip="悬浮显示 2FA 密钥，点击复制" />
              </div>
            </div>
            <div className="detail-panel__item detail-panel__item--full">
              <div className="detail-panel__label">Recovery Codes</div>
              <div className="detail-panel__value">
                {detailRow.recovery_codes?.length ? detailRow.recovery_codes.join('\n') : '-'}
              </div>
            </div>
            <div className="detail-panel__item">
              <div className="detail-panel__label">创建时间</div>
              <div className="detail-panel__value">{formatDateTime(detailRow.created_at)}</div>
            </div>
            <div className="detail-panel__item">
              <div className="detail-panel__label">更新时间</div>
              <div className="detail-panel__value">{formatDateTime(detailRow.updated_at)}</div>
            </div>
            <div className="detail-panel__item">
              <div className="detail-panel__label">最近导出</div>
              <div className="detail-panel__value">
                {detailRow.last_exported_at ? formatDateTime(detailRow.last_exported_at) : '-'}
              </div>
            </div>
            <div className="detail-panel__item detail-panel__item--full">
              <div className="detail-panel__label">备注</div>
              <div className="detail-panel__value">{detailRow.remark || '-'}</div>
            </div>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
