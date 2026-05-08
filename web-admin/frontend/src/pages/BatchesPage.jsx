import React, { useEffect, useState } from 'react';
import { Card, Select, Space, Table, Tag } from 'antd';
import { fetchBatches } from '../services/api';
import { formatDateTime } from '../utils/datetime';

export default function BatchesPage() {
  const [rows, setRows] = useState([]);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [batchType, setBatchType] = useState();

  const loadData = async (page = pagination.current, pageSize = pagination.pageSize, nextType = batchType) => {
    const { data } = await fetchBatches({ page, page_size: pageSize, batch_type: nextType });
    setRows(data.items);
    setPagination({ current: data.page, pageSize: data.page_size, total: data.total });
  };

  useEffect(() => {
    loadData(1, pagination.pageSize, batchType);
  }, [batchType]);

  return (
    <div className="page-shell">
      <div className="page-header">
        <h2>批次中心</h2>
        <p>查看邮箱导入、GitHub 推送和导出批次，方便追踪数据来源和处理结果。</p>
      </div>
      <Card
        className="table-card"
        extra={
          <Space className="table-toolbar" wrap>
            <Select
              allowClear
              placeholder="按批次类型筛选"
              style={{ width: 200 }}
              options={[
                { label: '邮箱导入', value: 'mail_import' },
                { label: 'GitHub 推送', value: 'github_push' },
                { label: 'GitHub 导出', value: 'github_export' },
              ]}
              value={batchType}
              onChange={setBatchType}
            />
          </Space>
        }
      >
        <Table
          className="management-table"
          size="middle"
          rowKey="id"
          dataSource={rows}
          scroll={{ x: 1040 }}
          sticky
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            onChange: (page, pageSize) => loadData(page, pageSize),
          }}
          columns={[
            { title: '批次号', dataIndex: 'batch_no', width: 220, ellipsis: true },
            { title: '批次类型', dataIndex: 'batch_type', width: 140, render: (value) => <Tag>{value}</Tag> },
            { title: '来源', dataIndex: 'source', width: 120, render: (value) => <Tag color="blue">{value}</Tag> },
            { title: '客户端', dataIndex: 'client_name', width: 180, ellipsis: true, render: (value) => value || '-' },
            { title: '总数', dataIndex: 'total_count', width: 100 },
            { title: '成功', dataIndex: 'success_count', width: 100 },
            { title: '重复', dataIndex: 'duplicate_count', width: 100 },
            { title: '创建时间', dataIndex: 'created_at', width: 180, render: formatDateTime },
          ]}
        />
      </Card>
    </div>
  );
}
