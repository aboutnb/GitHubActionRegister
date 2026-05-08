import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Drawer,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
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
  importGitHubAccounts,
  updateGitHubAccount,
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

function parseGitHubImportLine(line) {
  const raw = String(line || '').trim();
  if (!raw) return null;
  const parts = raw.split('---').map((item) => item.trim());
  if (parts.length < 3 || !parts[0] || !parts[1]) {
    throw new Error('导入格式应为：账号---密码---2FA密钥/NO_2FA---绑定邮箱（可选）');
  }
  return {
    github_login: parts[0],
    github_username: parts[0],
    github_password: parts[1],
    totp_secret: parts[2] || 'NO_2FA',
    bind_email: parts[3] || parts[0],
    raw_line: raw,
  };
}

export default function GitHubAccountsPage() {
  const [filters, setFilters] = usePersistentState('github_accounts_filters', {
    query: '',
    statusFilter: undefined,
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
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailRow, setDetailRow] = useState(null);
  const [editingRow, setEditingRow] = useState(null);
  const [loading, setLoading] = useState(false);
  const query = filters.query;
  const statusFilter = filters.statusFilter;
  const twoFaFilter = filters.twoFaFilter;
  const ageBucket = filters.ageBucket;
  const sortBy = filters.sortBy;
  const sortOrder = filters.sortOrder;
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [form] = Form.useForm();
  const [importForm] = Form.useForm();
  const selectedCount = selectedRowKeys.length;

  const loadData = async (
    page = pagination.current,
    pageSize = pagination.pageSize,
    nextQuery = query,
    nextStatus = statusFilter,
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
      two_fa_enabled: nextTwoFa,
      age_bucket: nextAgeBucket || undefined,
      sort_by: nextSortBy || undefined,
      sort_order: nextSortOrder || undefined,
    });
    setRows(data.items);
    setPagination({ current: data.page, pageSize: data.page_size, total: data.total });
  };

  useEffect(() => {
    loadData(1, pagination.pageSize, query, statusFilter, twoFaFilter, ageBucket);
  }, [query, statusFilter, twoFaFilter, ageBucket, sortBy, sortOrder]);

  const openCreate = () => {
    setEditingRow(null);
    form.resetFields();
    form.setFieldsValue({ status: 'active', two_fa_enabled: true });
    setEditorOpen(true);
  };

  const openEdit = (row) => {
    setEditingRow(row);
    form.setFieldsValue({
      github_login: row.github_login,
      github_username: row.github_username,
      bind_email: row.bind_email,
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

  const resetFilters = () => {
    setFilters({
      query: '',
      statusFilter: undefined,
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
    row.github_login || '',
    row.github_password || '',
    row.totp_secret || 'NO_2FA',
    row.bind_email || '',
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
        title: '账号',
        dataIndex: 'github_login',
        width: 240,
        ellipsis: true,
        sorter: true,
        sortOrder: sortBy === 'github_login' ? sortOrder : null,
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
        title: '绑定邮箱',
        dataIndex: 'bind_email',
        width: 240,
        ellipsis: true,
        sorter: true,
        sortOrder: sortBy === 'bind_email' ? sortOrder : null,
        render: (value) => value || '-',
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
        width: 180,
        fixed: 'right',
        align: 'right',
        className: 'actions-column',
        render: (_, row) => (
          <Space className="table-action-bar">
            <Button type="link" onClick={() => openDetail(row)}>
              详情
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
    [sortBy, sortOrder],
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
          <Space className="table-toolbar" wrap>
            <Input.Search
              allowClear
              placeholder="搜索用户名 / 账号 / 备注"
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
            <Button onClick={() => setImportOpen(true)}>批量导入</Button>
            <Button onClick={handleExport}>导出可用账号</Button>
            <Button type="primary" onClick={openCreate}>
              新增 GitHub 账号
            </Button>
          </Space>
        }
      >
        {selectedCount > 0 && (
          <div className="selection-toolbar">
            <Space size={12}>
              <span className="selection-toolbar__count">已选 {selectedCount} 条 GitHub 账号</span>
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
          scroll={{ x: 1880 }}
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
                复制全部（账号---密码---2FA）
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
            rowKey={(row) => `${row.github_login}-${row.github_username || 'no-user'}`}
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
            extra="每行一条，格式：账号---密码---2FA密钥---绑定邮箱。绑定邮箱可选，未填写时默认回填当前账号。未开启 2FA 的账号请填写 NO_2FA。"
          >
            <Input.TextArea
              rows={14}
              placeholder={`JeanPainter961956@outlook.com---MZVcd673@Git2026---3KFJPTQ2WSZAOUP6---JeanPainter961956@outlook.com\nWilliamWatson148@outlook.com---TLFovyw60@Git2026---NO_2FA---WilliamWatson148@outlook.com`}
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
            label="账号"
            name="github_login"
            rules={[{ required: true, message: '请输入账号' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item label="用户名" name="github_username">
            <Input />
          </Form.Item>
          <Form.Item
            label="绑定邮箱"
            name="bind_email"
            extra="填写后会自动同步邮箱资产状态；留空时不会建立显式绑定。"
          >
            <Input placeholder="例如：JeanPainter961956@outlook.com" />
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
              <div className="detail-panel__label">账号</div>
              <div className="detail-panel__value">{detailRow.github_login}</div>
            </div>
            <div className="detail-panel__item">
              <div className="detail-panel__label">用户名</div>
              <div className="detail-panel__value">{detailRow.github_username || '-'}</div>
            </div>
            <div className="detail-panel__item">
              <div className="detail-panel__label">绑定邮箱</div>
              <div className="detail-panel__value">{detailRow.bind_email || '-'}</div>
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
