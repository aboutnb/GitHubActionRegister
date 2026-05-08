import React, { useEffect, useState } from 'react';
import { Card, Select, Space, Table, Tag } from 'antd';
import { fetchAuditLogs } from '../services/api';
import { formatDateTime } from '../utils/datetime';

export default function AuditLogsPage() {
  const [rows, setRows] = useState([]);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [targetType, setTargetType] = useState();

  const loadData = async (page = pagination.current, pageSize = pagination.pageSize, nextTarget = targetType) => {
    const { data } = await fetchAuditLogs({ page, page_size: pageSize, target_type: nextTarget });
    setRows(data.items);
    setPagination({ current: data.page, pageSize: data.page_size, total: data.total });
  };

  useEffect(() => {
    loadData(1, pagination.pageSize, targetType);
  }, [targetType]);

  return (
    <div className="page-shell">
      <div className="page-header">
        <h2>审计日志</h2>
        <p>记录敏感操作，包括导出账号、查看凭证、批量导入和账户修改。</p>
      </div>
      <Card
        className="table-card"
        extra={
          <Space className="table-toolbar" wrap>
            <Select
              allowClear
              placeholder="按目标类型筛选"
              style={{ width: 200 }}
              options={[
                { label: '邮箱资产', value: 'mail_account' },
                { label: 'GitHub 账号', value: 'github_account' },
                { label: '桌面客户端', value: 'desktop_client' },
              ]}
              value={targetType}
              onChange={setTargetType}
            />
          </Space>
        }
      >
        <Table
          className="management-table"
          size="middle"
          rowKey="id"
          dataSource={rows}
          scroll={{ x: 1120 }}
          sticky
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            onChange: (page, pageSize) => loadData(page, pageSize),
          }}
          columns={[
            { title: '操作者类型', dataIndex: 'operator_type', width: 140, render: (value) => <Tag>{value}</Tag> },
            { title: '操作者 ID', dataIndex: 'operator_id', width: 120 },
            { title: '动作', dataIndex: 'action', width: 180, ellipsis: true },
            { title: '目标类型', dataIndex: 'target_type', width: 160 },
            { title: '目标 ID', dataIndex: 'target_id', width: 120, render: (value) => value || '-' },
            {
              title: '详情',
              dataIndex: 'details',
              width: 300,
              ellipsis: true,
              render: (value) => (value ? JSON.stringify(value) : '-'),
            },
            { title: '时间', dataIndex: 'created_at', width: 180, render: formatDateTime },
          ]}
        />
      </Card>
    </div>
  );
}
