import React, { useEffect, useState } from 'react';
import { Card, Select, Space, Table, Tag } from 'antd';
import { fetchSyncLogs } from '../services/api';
import { formatDateTime } from '../utils/datetime';

export default function LogsPage() {
  const [rows, setRows] = useState([]);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [action, setAction] = useState();

  const loadData = async (page = pagination.current, pageSize = pagination.pageSize, nextAction = action) => {
    const { data } = await fetchSyncLogs({ page, page_size: pageSize, action: nextAction });
    setRows(data.items);
    setPagination({ current: data.page, pageSize: data.page_size, total: data.total });
  };

  useEffect(() => {
    loadData(1, pagination.pageSize, action);
  }, [action]);

  return (
    <div className="page-shell">
      <div className="page-header">
        <h2>同步日志</h2>
        <p>查看桌面端拉邮箱、推 GitHub 成品账号的历史记录和结果汇总。</p>
      </div>
      <Card
        className="table-card"
        extra={
          <Space className="table-toolbar" wrap>
            <Select
              allowClear
              placeholder="按动作筛选"
              style={{ width: 180 }}
              options={[
                { label: '拉邮箱', value: 'pull_mail' },
                { label: '推 GitHub', value: 'push_github' },
                { label: '心跳', value: 'heartbeat' },
              ]}
              value={action}
              onChange={setAction}
            />
          </Space>
        }
      >
        <Table
          className="management-table"
          size="middle"
          rowKey="id"
          dataSource={rows}
          scroll={{ x: 1000 }}
          sticky
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            onChange: (page, pageSize) => loadData(page, pageSize),
          }}
          columns={[
            { title: '客户端', dataIndex: 'client_name', width: 180, ellipsis: true, render: (value) => value || '-' },
            { title: '动作', dataIndex: 'action', width: 130, render: (value) => <Tag>{value}</Tag> },
            { title: '请求量', dataIndex: 'payload_count', width: 100 },
            { title: '成功', dataIndex: 'success_count', width: 100 },
            { title: '失败', dataIndex: 'failed_count', width: 100 },
            { title: '说明', dataIndex: 'message', width: 280, ellipsis: true, render: (value) => value || '-' },
            { title: '时间', dataIndex: 'created_at', width: 180, render: formatDateTime },
          ]}
        />
      </Card>
    </div>
  );
}
