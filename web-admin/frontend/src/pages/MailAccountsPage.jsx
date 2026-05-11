import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Drawer,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd';
import {
  ClockCircleOutlined,
  InboxOutlined,
  GlobalOutlined,
  MailOutlined,
  ReloadOutlined,
  UserOutlined,
} from '@ant-design/icons';
import {
  bulkDeleteMailAccounts,
  bulkUpdateMailStatus,
  createMailAccount,
  deleteMailAccount,
  fetchMailAccounts,
  fetchMailMessages,
  importMailAccounts,
  updateMailAccount,
} from '../services/api';
import SensitiveValue from '../components/SensitiveValue';
import { usePersistentState } from '../hooks/usePersistentState';
import { formatDateTime } from '../utils/datetime';

const statusColor = {
  idle: 'blue',
  registered: 'cyan',
  disabled: 'default',
};

const statusOptions = [
  { label: '未注册', value: 'idle' },
  { label: '已注册', value: 'registered' },
  { label: '禁用', value: 'disabled' },
];

const receiveModeOptions = [
  { label: '官方收件', value: 'official' },
  { label: '小水滴收件', value: 'xiaoshuidi' },
];

function parseMailImportLine(line, receiveMode) {
  if (line.includes('----')) {
    const parts = line.split('----');
    const compactParts = parts.filter((part) => part !== '');
    if (receiveMode === 'official') {
      if (compactParts.length !== 4) {
        throw new Error('官方收件格式应为：邮箱----密码----account_id----token');
      }
    } else if (receiveMode === 'xiaoshuidi') {
      if (compactParts.length < 4) {
        throw new Error('小水滴收件格式应为：邮箱----密码----...----account_id----token');
      }
    } else {
      throw new Error('请先选择收件方式');
    }
    const email = compactParts[0];
    const password = compactParts[1];

    return {
      email,
      password,
      raw_line: line,
      receive_mode: receiveMode,
    };
  }

  if (!receiveMode) {
    throw new Error('请先选择收件方式');
  }
  const [email, password] = line.split(',').map((part) => part.trim());
  return { email, password, receive_mode: receiveMode };
}

function normalizeMailStatus(value) {
  return value || 'idle';
}

export default function MailAccountsPage() {
  const [filters, setFilters] = usePersistentState('mail_accounts_filters', {
    query: '',
    statusFilter: undefined,
    receiveModeFilter: undefined,
    sortBy: undefined,
    sortOrder: undefined,
  });
  const [rows, setRows] = useState([]);
  const [recentResult, setRecentResult] = useState(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importFileName, setImportFileName] = useState('');
  const [editorOpen, setEditorOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailRow, setDetailRow] = useState(null);
  const [mailDrawerOpen, setMailDrawerOpen] = useState(false);
  const [mailDrawerLoading, setMailDrawerLoading] = useState(false);
  const [mailDrawerRow, setMailDrawerRow] = useState(null);
  const [mailFetchResult, setMailFetchResult] = useState(null);
  const [selectedMessageId, setSelectedMessageId] = useState(null);
  const [editingRow, setEditingRow] = useState(null);
  const [loading, setLoading] = useState(false);
  const query = filters.query;
  const statusFilter = filters.statusFilter;
  const receiveModeFilter = filters.receiveModeFilter;
  const sortBy = filters.sortBy;
  const sortOrder = filters.sortOrder;
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [importForm] = Form.useForm();
  const [editorForm] = Form.useForm();
  const selectedCount = selectedRowKeys.length;

  const readFileAsText = (file) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(new Error('文件读取失败'));
      reader.readAsText(file, 'utf-8');
    });

  const loadData = async (
    page = pagination.current,
    pageSize = pagination.pageSize,
    nextQuery = query,
    nextStatus = statusFilter,
    nextReceiveMode = receiveModeFilter,
  ) => {
    const { data } = await fetchMailAccounts({
      page,
      page_size: pageSize,
      q: nextQuery || undefined,
      status: nextStatus || undefined,
      receive_mode: nextReceiveMode || undefined,
      sort_by: sortBy || undefined,
      sort_order: sortOrder || undefined,
    });
    setRows(data.items);
    setPagination({ current: data.page, pageSize: data.page_size, total: data.total });
  };

  useEffect(() => {
    loadData(1, pagination.pageSize, query, statusFilter, receiveModeFilter);
  }, [query, statusFilter, receiveModeFilter, sortBy, sortOrder]);

  const openCreate = () => {
    setEditingRow(null);
    editorForm.resetFields();
    editorForm.setFieldsValue({ status: 'idle', receive_mode: 'official', raw_line: '' });
    setEditorOpen(true);
  };

  const openEdit = (row) => {
    setEditingRow(row);
    editorForm.setFieldsValue({
      email: row.email,
      receive_mode: row.receive_mode || 'official',
      status: row.status,
      remark: row.remark,
      password: '',
      raw_line: row.raw_line || '',
      client_id: row.client_id || '',
      access_token: row.access_token || '',
    });
    setEditorOpen(true);
  };

  const openDetail = (row) => {
    setDetailRow(row);
    setDetailOpen(true);
  };

  const handleOpenMailDrawer = async (row) => {
    setMailDrawerRow(row);
    setMailFetchResult(null);
    setSelectedMessageId(null);
    setMailDrawerOpen(true);
    await handleFetchMailMessages(row);
  };

  const handleFetchMailMessages = async (row = mailDrawerRow) => {
    if (!row?.id) return;
    setMailDrawerLoading(true);
    try {
      const { data } = await fetchMailMessages(row.id);
      setMailFetchResult(data);
      if (data.messages?.length) {
        setSelectedMessageId((prev) => {
          const exists = data.messages.some((item) => item.id === prev);
          return exists ? prev : data.messages[0].id;
        });
      } else {
        setSelectedMessageId(null);
      }
    } catch (error) {
      setMailFetchResult(null);
      setSelectedMessageId(null);
      message.error(error?.response?.data?.detail || '取件失败');
    } finally {
      setMailDrawerLoading(false);
    }
  };

  const handleImport = async (values) => {
    setLoading(true);
    try {
      if (!values.receive_mode) {
        throw new Error('请选择收件方式');
      }
      const items = values.lines
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => parseMailImportLine(line, values.receive_mode));
      const { data } = await importMailAccounts({ receive_mode: values.receive_mode, items });
      message.success(`导入完成：${data.success_count} 条，重复 ${data.duplicate_count} 条`);
      setRecentResult({
        type: 'import',
        title: '最近一次导入结果',
        summary: `本次导入 ${data.total_count} 条，成功 ${data.success_count} 条，重复 ${data.duplicate_count} 条`,
        meta: [
          { label: '批次号', value: data.batch_no || '-' },
          { label: '总数', value: data.total_count },
          { label: '成功', value: data.success_count },
          { label: '重复', value: data.duplicate_count },
        ],
      });
      setImportOpen(false);
      importForm.resetFields();
      loadData();
    } catch (error) {
      message.error(error?.response?.data?.detail || '导入失败');
    } finally {
      setLoading(false);
    }
  };

  const handleImportFile = async (file) => {
    try {
      const text = await readFileAsText(file);
      importForm.setFieldsValue({
        lines: text.replace(/\r\n/g, '\n').replace(/\r/g, '\n'),
      });
      setImportFileName(file.name);
      message.success(`已读取文件：${file.name}`);
    } catch (error) {
      message.error(error?.message || '读取文件失败');
    }
    return false;
  };

  const handleSave = async (values) => {
    setLoading(true);
    try {
      if (!values.receive_mode) {
        throw new Error('请选择收件方式');
      }
      if (editingRow) {
        const { data } = await updateMailAccount(editingRow.id, values);
        message.success('邮箱已更新');
        setRecentResult({
          type: 'update',
          title: '最近一次操作结果',
          summary: `已更新邮箱 ${data.email}`,
          meta: [
            { label: '邮箱', value: data.email },
            { label: '状态', value: data.status },
            { label: '收件方式', value: data.receive_mode === 'xiaoshuidi' ? '小水滴收件' : '官方收件' },
            { label: '更新时间', value: data.updated_at || '-' },
          ],
        });
      } else {
        const { data } = await createMailAccount(values);
        message.success('邮箱已创建');
        setRecentResult({
          type: 'create',
          title: '最近一次操作结果',
          summary: `已新增邮箱 ${data.email}`,
          meta: [
            { label: '邮箱', value: data.email },
            { label: '状态', value: data.status },
            { label: '收件方式', value: data.receive_mode === 'xiaoshuidi' ? '小水滴收件' : '官方收件' },
            { label: '更新时间', value: data.updated_at || '-' },
          ],
        });
      }
      setEditorOpen(false);
      editorForm.resetFields();
      loadData();
    } catch (error) {
      message.error(error?.response?.data?.detail || '保存失败');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (row) => {
    try {
      await deleteMailAccount(row.id);
      message.success('邮箱已删除');
      setRecentResult({
        type: 'delete',
        title: '最近一次操作结果',
        summary: `已删除邮箱 ${row.email}`,
        meta: [
          { label: '邮箱', value: row.email },
          { label: '状态', value: row.status },
          { label: '备注', value: row.remark || '-' },
        ],
      });
      loadData();
    } catch (error) {
      message.error(error?.response?.data?.detail || '删除失败');
    }
  };

  const handleBulkStatus = async (status) => {
    if (!selectedRowKeys.length) {
      message.warning('请先选择邮箱');
      return;
    }
    await bulkUpdateMailStatus({ ids: selectedRowKeys, status });
    message.success('批量状态更新完成');
    setRecentResult({
      type: 'bulk-status',
      title: '最近一次操作结果',
      summary: `已将 ${selectedRowKeys.length} 条邮箱更新为 ${status}`,
      meta: [
        { label: '操作类型', value: '批量状态更新' },
        { label: '目标状态', value: status },
        { label: '影响条数', value: selectedRowKeys.length },
      ],
    });
    setSelectedRowKeys([]);
    loadData();
  };

  const handleBulkDelete = async () => {
    if (!selectedRowKeys.length) {
      message.warning('请先选择邮箱');
      return;
    }
    const { data } = await bulkDeleteMailAccounts({ ids: selectedRowKeys });
    message.success(`已删除 ${data.deleted} 条邮箱`);
    setRecentResult({
      type: 'bulk-delete',
      title: '最近一次操作结果',
      summary: `已删除 ${data.deleted} 条邮箱`,
      meta: [
        { label: '操作类型', value: '批量删除' },
        { label: '影响条数', value: data.deleted },
      ],
    });
    setSelectedRowKeys([]);
    loadData();
  };

  const resetFilters = () => {
    setFilters({
      query: '',
      statusFilter: undefined,
      receiveModeFilter: undefined,
      sortBy: undefined,
      sortOrder: undefined,
    });
  };

  const clearSelection = () => {
    setSelectedRowKeys([]);
  };

  const selectedMessage = useMemo(() => {
    if (!mailFetchResult?.messages?.length) return null;
    return (
      mailFetchResult.messages.find((item) => item.id === selectedMessageId) ||
      mailFetchResult.messages[0]
    );
  }, [mailFetchResult, selectedMessageId]);

  const handleTableChange = (nextPagination, _tableFilters, sorter) => {
    const sorterValue = Array.isArray(sorter) ? sorter[0] : sorter;
    setFilters((prev) => ({
      ...prev,
      sortBy: sorterValue?.order ? sorterValue.field : undefined,
      sortOrder: sorterValue?.order || undefined,
    }));
    loadData(
      nextPagination.current,
      nextPagination.pageSize,
      query,
      statusFilter,
      receiveModeFilter,
    );
  };

  const columns = useMemo(
    () => [
      { title: '邮箱', dataIndex: 'email', width: 240, ellipsis: true, sorter: true, sortOrder: sortBy === 'email' ? sortOrder : null },
      {
        title: '状态',
        dataIndex: 'status',
        width: 110,
        sorter: true,
        sortOrder: sortBy === 'status' ? sortOrder : null,
        render: (value) => {
          const normalizedValue = normalizeMailStatus(value);
          const labelMap = {
            idle: '未注册',
            registered: '已注册',
            disabled: '禁用',
          };
          return <Tag color={statusColor[normalizedValue] || 'default'}>{labelMap[normalizedValue] || normalizedValue}</Tag>;
        },
      },
      {
        title: '收件方式',
        dataIndex: 'receive_mode',
        width: 120,
        render: (value) => {
          if (value === 'official') return '官方收件';
          if (value === 'xiaoshuidi') return '小水滴收件';
          return '-';
        },
      },
      {
        title: 'Client ID',
        dataIndex: 'client_id',
        width: 180,
        ellipsis: true,
        render: (value) => value || '-',
      },
      {
        title: 'Token',
        dataIndex: 'has_access_token',
        width: 96,
        render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? '已保存' : '无'}</Tag>,
      },
      { title: '更新时间', dataIndex: 'updated_at', width: 170, sorter: true, sortOrder: sortBy === 'updated_at' ? sortOrder : null, render: formatDateTime },
      {
        title: '密码',
        key: 'password',
        width: 180,
        render: (_, row) => <SensitiveValue value={row.password} tooltip="悬浮显示邮箱密码，点击复制" />,
      },
      { title: '备注', dataIndex: 'remark', width: 220, ellipsis: true, render: (value) => value || '-' },
      {
        title: '操作',
        key: 'actions',
        width: 230,
        fixed: 'right',
        align: 'right',
        className: 'actions-column',
        render: (_, row) => (
          <Space className="table-action-bar">
            <Button type="link" onClick={() => handleOpenMailDrawer(row)}>
              取件
            </Button>
            <Button type="link" onClick={() => openDetail(row)}>
              详情
            </Button>
            <Button type="link" onClick={() => openEdit(row)}>
              编辑
            </Button>
            <Popconfirm title="确认删除这个邮箱吗？" onConfirm={() => handleDelete(row)}>
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

  return (
    <div className="page-shell">
      <div className="page-header">
        <h2>邮箱资产</h2>
        <p>支持邮箱资产的增删改查，并为未来邮件收发和验证码提取能力保留结构。</p>
      </div>
      <Card
        className="table-card"
        extra={
          <Space className="table-toolbar" wrap>
            <Input.Search
              allowClear
              placeholder="搜索邮箱 / Client ID / 备注"
              style={{ width: 260 }}
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
              placeholder="收件方式"
              style={{ width: 150 }}
              options={receiveModeOptions}
              value={receiveModeFilter}
              onChange={(value) => setFilters((prev) => ({ ...prev, receiveModeFilter: value }))}
            />
            <Button onClick={resetFilters}>重置筛选</Button>
            <Popconfirm
              title={`确认将选中的 ${selectedRowKeys.length} 条邮箱批量禁用吗？`}
              description="状态会更新为 disabled，可在列表中继续筛选和恢复。"
              onConfirm={() => handleBulkStatus('disabled')}
              okText="确认禁用"
              cancelText="取消"
            >
              <Button disabled={!selectedRowKeys.length}>批量禁用</Button>
            </Popconfirm>
            <Popconfirm
              title={`确认批量删除选中的 ${selectedRowKeys.length} 条邮箱吗？`}
              description="删除后凭证和关联记录会一并移除。"
              onConfirm={handleBulkDelete}
              okText="确认删除"
              cancelText="取消"
            >
              <Button danger>批量删除</Button>
            </Popconfirm>
            <Button onClick={() => setImportOpen(true)}>批量导入</Button>
            <Button type="primary" onClick={openCreate}>
              新增邮箱
            </Button>
          </Space>
        }
      >
        {selectedCount > 0 && (
          <div className="selection-toolbar">
            <Space size={12}>
              <span className="selection-toolbar__count">已选 {selectedCount} 条邮箱</span>
              <Popconfirm
                title={`确认将选中的 ${selectedCount} 条邮箱批量禁用吗？`}
                description="状态会更新为 disabled，可在列表中继续筛选和恢复。"
                onConfirm={() => handleBulkStatus('disabled')}
                okText="确认禁用"
                cancelText="取消"
              >
                <Button size="small">批量禁用</Button>
              </Popconfirm>
              <Popconfirm
                title={`确认批量删除选中的 ${selectedCount} 条邮箱吗？`}
                description="删除后凭证和关联记录会一并移除。"
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
          scroll={{ x: 1200 }}
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

      {recentResult && (
        <Card
          style={{ marginTop: 16 }}
          title={recentResult.title}
          extra={
            <Button size="small" onClick={() => setRecentResult(null)}>
              清空结果
            </Button>
          }
        >
          <div className="result-panel">
            <div className="result-panel__summary">{recentResult.summary}</div>
            <div className="result-panel__grid">
              {recentResult.meta.map((item) => (
                <div key={`${recentResult.type}-${item.label}`} className="result-panel__item">
                  <div className="result-panel__label">{item.label}</div>
                  <div className="result-panel__value">{item.value}</div>
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}

      <Drawer
        title="批量导入邮箱"
        width={520}
        open={importOpen}
        onClose={() => {
          setImportOpen(false);
          setImportFileName('');
        }}
        destroyOnClose
      >
        <Form layout="vertical" form={importForm} onFinish={handleImport}>
          <Form.Item
            label="收件方式"
            name="receive_mode"
            initialValue="official"
            rules={[{ required: true, message: '请选择收件方式' }]}
          >
            <Select options={receiveModeOptions} />
          </Form.Item>
          <Upload.Dragger
            accept=".txt,.csv,.log,.json"
            beforeUpload={handleImportFile}
            showUploadList={false}
            multiple={false}
            style={{ marginBottom: 16 }}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">点击打开文件，或拖拽文件到这里</p>
            <p className="ant-upload-hint">读取后会自动填充到下方导入内容框。</p>
          </Upload.Dragger>
          <Form.Item
            label="多行导入内容"
            name="lines"
            rules={[{ required: true, message: '请输入多行导入内容' }]}
            extra={
              importFileName
                ? `当前已加载文件：${importFileName}。每行一条，先选择收件方式。官方收件：邮箱----密码----account_id----token；小水滴收件：邮箱----密码----...----account_id----token`
                : '每行一条，先选择收件方式。官方收件：邮箱----密码----account_id----token；小水滴收件：邮箱----密码----...----account_id----token'
            }
          >
            <Input.TextArea
              rows={14}
              placeholder={`victoriavpatiencei1970@hotmail.com----zehdss02608----9e5f94bc-e8a4-4e73-b8be-63364c29d753----token\nSamuelMeade94131@outlook.com----WEqnqd817----...----9e5f94bc-e8a4-4e73-b8be-63364c29d753----token`}
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
        title={editingRow ? '编辑邮箱' : '新增邮箱'}
        open={editorOpen}
        onCancel={() => setEditorOpen(false)}
        footer={null}
        destroyOnClose
      >
        <Form layout="vertical" form={editorForm} onFinish={handleSave}>
          <Form.Item
            label="收件方式"
            name="receive_mode"
            rules={[{ required: true, message: '请选择收件方式' }]}
          >
            <Select options={receiveModeOptions} />
          </Form.Item>
          <Form.Item
            label="原始导入串"
            name="raw_line"
            extra="如果填写原始串，将按所选收件方式校验并自动解析邮箱、密码、Client ID 和 Token。"
          >
            <Input.TextArea rows={3} placeholder="邮箱----密码----account_id----token 或 小水滴原始串" />
          </Form.Item>
          <Form.Item label="邮箱" name="email" rules={[{ required: true, message: '请输入邮箱' }]}>
            <Input />
          </Form.Item>
          <Form.Item
            label={editingRow ? '新密码' : '密码'}
            name="password"
            rules={editingRow ? [] : [{ required: true, message: '请输入密码' }]}
          >
            <Input.Password placeholder={editingRow ? '留空则保持不变' : '请输入密码'} />
          </Form.Item>
          <Form.Item
            label="Client ID"
            name="client_id"
            extra="不填原始导入串时，可直接填写 Client ID。"
          >
            <Input placeholder="例如：9e5f94bc-e8a4-4e73-b8be-63364c29d753" />
          </Form.Item>
          <Form.Item
            label="Access Token"
            name="access_token"
            extra="不填原始导入串时，可直接填写 Token。"
          >
            <Input.TextArea rows={4} placeholder="请输入 Token" />
          </Form.Item>
          <Form.Item label="状态" name="status" rules={[{ required: true, message: '请选择状态' }]}>
            <Select options={statusOptions} />
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
        title={mailDrawerRow ? `邮件列表 · ${mailDrawerRow.email}` : '邮件列表'}
        width={980}
        className="mail-fetch-drawer"
        open={mailDrawerOpen}
        onClose={() => setMailDrawerOpen(false)}
        destroyOnClose={false}
        extra={(
          <Button
            icon={<ReloadOutlined />}
            loading={mailDrawerLoading}
            onClick={() => handleFetchMailMessages()}
          >
            重新取件
          </Button>
        )}
      >
        <div className="mail-fetch-layout">
          <div className="mail-fetch-layout__sidebar">
            <div className="mail-fetch-layout__summary">
              <div className="mail-fetch-layout__summary-title">
                <MailOutlined />
                <span>{mailDrawerRow?.email || '未选择邮箱'}</span>
              </div>
              <div className="mail-fetch-layout__summary-meta">
                <span>收件方式：{mailDrawerRow?.receive_mode === 'xiaoshuidi' ? '小水滴收件' : '官方收件'}</span>
                <span>邮件数：{mailFetchResult?.messages?.length || 0}</span>
              </div>
            </div>
            {mailFetchResult?.note ? (
              <Alert
                className="mail-fetch-layout__note"
                type="info"
                showIcon
                message={mailFetchResult.note}
              />
            ) : null}
            <List
              className="mail-message-list"
              loading={mailDrawerLoading}
              locale={{ emptyText: '暂无邮件' }}
              dataSource={mailFetchResult?.messages || []}
              renderItem={(item, index) => (
                <List.Item
                  className={
                    item.id === (selectedMessage?.id || selectedMessageId)
                      ? 'mail-message-list__item is-active'
                      : 'mail-message-list__item'
                  }
                  onClick={() => setSelectedMessageId(item.id)}
                >
                  <div className="mail-message-card">
                    <div className="mail-message-card__main">
                      <div className="mail-message-card__title-row">
                        <div className="mail-message-card__subject">{item.subject || '(无主题)'}</div>
                      </div>
                      <div className="mail-message-card__meta">
                        <span className="mail-message-card__meta-item">
                          <UserOutlined />
                          <span>{item.sender || '-'}</span>
                        </span>
                        <span className="mail-message-card__meta-item">
                          <ClockCircleOutlined />
                          <span>{item.received_at_beijing || item.received_at_utc || '-'}</span>
                        </span>
                      </div>
                    </div>
                    {index === 0 ? (
                      <div className="mail-message-card__corner" aria-hidden="true">
                        <span>NEW</span>
                      </div>
                    ) : null}
                  </div>
                </List.Item>
              )}
            />
          </div>
          <div className="mail-fetch-layout__content">
            {selectedMessage ? (
              <div className="mail-message-detail">
                <div className="mail-message-detail__hero">
                  <div className="mail-message-detail__eyebrow">
                    <Tag color="processing" bordered={false}>邮件详情</Tag>
                    <span>{mailFetchResult?.provider === 'xiaoshuidi' ? '小水滴取件' : '收件服务'}</span>
                  </div>
                  <div className="mail-message-detail__headline">
                    {selectedMessage.subject || '(无主题)'}
                  </div>
                  <div className="mail-message-detail__subline">
                    <span>
                      <UserOutlined />
                      <strong>发件人：</strong>
                      {selectedMessage.sender || '-'}
                    </span>
                    <span>
                      <MailOutlined />
                      <strong>收件人：</strong>
                      {selectedMessage.recipient || '-'}
                    </span>
                  </div>
                </div>

                <div className="mail-message-detail__facts">
                  <div className="mail-message-fact">
                    <div className="mail-message-fact__label">
                      <GlobalOutlined />
                      <span>接收时间 [UTC标准时间]</span>
                    </div>
                    <div className="mail-message-fact__value">{selectedMessage.received_at_utc || '-'}</div>
                  </div>
                  <div className="mail-message-fact">
                    <div className="mail-message-fact__label">
                      <ClockCircleOutlined />
                      <span>接收时间 [北京时间]</span>
                    </div>
                    <div className="mail-message-fact__value">{selectedMessage.received_at_beijing || '-'}</div>
                  </div>
                  <div className="mail-message-fact">
                    <div className="mail-message-fact__label">
                      <UserOutlined />
                      <span>发 件 人</span>
                    </div>
                    <div className="mail-message-fact__value">{selectedMessage.sender || '-'}</div>
                  </div>
                  <div className="mail-message-fact">
                    <div className="mail-message-fact__label">
                      <MailOutlined />
                      <span>收 件 人</span>
                    </div>
                    <div className="mail-message-fact__value">{selectedMessage.recipient || '-'}</div>
                  </div>
                </div>
                <Card
                  className="mail-message-detail__body"
                  title="邮件正文"
                  size="small"
                >
                  <Typography.Paragraph className="mail-message-detail__text">
                    {selectedMessage.content_text || '暂无正文文本'}
                  </Typography.Paragraph>
                  {selectedMessage.content_html ? (
                    <details className="mail-message-detail__html">
                      <summary>查看原始 HTML</summary>
                      <pre>{selectedMessage.content_html}</pre>
                    </details>
                  ) : null}
                </Card>
              </div>
            ) : (
              <div className="mail-fetch-layout__empty">
                {mailDrawerLoading ? '正在取件...' : '暂无可展示的邮件'}
              </div>
            )}
          </div>
        </div>
      </Drawer>

      <Drawer
        title="邮箱详情"
        width={520}
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
              <div className="detail-panel__label">收件方式</div>
              <div className="detail-panel__value">
                {detailRow.receive_mode === 'xiaoshuidi' ? '小水滴收件' : '官方收件'}
              </div>
            </div>
            <div className="detail-panel__item">
              <div className="detail-panel__label">Client ID</div>
              <div className="detail-panel__value">{detailRow.client_id || '-'}</div>
            </div>
            <div className="detail-panel__item">
              <div className="detail-panel__label">Token 状态</div>
              <div className="detail-panel__value">{detailRow.has_access_token ? '已保存' : '无'}</div>
            </div>
            <div className="detail-panel__item">
              <div className="detail-panel__label">密码</div>
              <div className="detail-panel__value">
                <SensitiveValue value={detailRow.password} tooltip="悬浮显示邮箱密码，点击复制" />
              </div>
            </div>
            <div className="detail-panel__item">
              <div className="detail-panel__label">更新时间</div>
              <div className="detail-panel__value">{formatDateTime(detailRow.updated_at)}</div>
            </div>
            <div className="detail-panel__item detail-panel__item--full">
              <div className="detail-panel__label">原始导入串</div>
              <div className="detail-panel__value detail-panel__value--code">
                {detailRow.raw_line || '-'}
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
