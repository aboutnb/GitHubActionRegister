import React, { useEffect, useState } from 'react';
import { Button, Card, Drawer, Form, Input, Popconfirm, Space, Table, Tag, Typography, message } from 'antd';
import { createDesktopClient, deleteDesktopClient, fetchDesktopClients } from '../services/api';

export default function ClientsPage() {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  const [created, setCreated] = useState(null);
  const [form] = Form.useForm();

  const loadData = async () => {
    const { data } = await fetchDesktopClients();
    setRows(data);
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleCreate = async (values) => {
    try {
      const { data } = await createDesktopClient(values);
      setCreated(data);
      message.success('客户端已创建，请立即保存 token');
      setOpen(false);
      form.resetFields();
      loadData();
    } catch (error) {
      message.error(error?.response?.data?.detail || '创建失败');
    }
  };

  const handleDelete = async (row) => {
    try {
      await deleteDesktopClient(row.id);
      message.success('客户端已删除');
      loadData();
    } catch (error) {
      message.error(error?.response?.data?.detail || '删除失败');
    }
  };

  return (
    <div className="page-shell">
      <div className="page-header">
        <h2>客户端密钥</h2>
        <p>管理桌面端调用管理平台接口所需的 API 密钥，仅用于鉴权识别。</p>
      </div>
      <Card
        className="table-card"
        extra={<Button type="primary" onClick={() => setOpen(true)}>新增客户端</Button>}
      >
        <Table
          className="management-table"
          size="middle"
          rowKey="id"
          dataSource={rows}
          scroll={{ x: 860 }}
          sticky
          pagination={{ pageSize: 20 }}
          columns={[
            { title: '名称', dataIndex: 'name', width: 220, ellipsis: true },
            { title: '状态', dataIndex: 'status', width: 120, render: (value) => <Tag color="green">{value}</Tag> },
            { title: '最近在线', dataIndex: 'last_seen_at', width: 180, render: (value) => value || '-' },
            { title: '最近 IP', dataIndex: 'last_ip', width: 160, render: (value) => value || '-' },
            { title: '创建时间', dataIndex: 'created_at', width: 180, render: (value) => value || '-' },
            {
              title: '操作',
              dataIndex: 'action',
              width: 120,
              fixed: 'right',
              render: (_, row) => (
                <Popconfirm
                  title="确认删除这个客户端？"
                  description="删除后该密钥将无法继续调用接口，但不会改动任何邮箱或 GitHub 账号状态。"
                  okText="删除"
                  okButtonProps={{ danger: true }}
                  cancelText="取消"
                  onConfirm={() => handleDelete(row)}
                >
                  <Button danger type="link" size="small">删除</Button>
                </Popconfirm>
              ),
            },
          ]}
        />
      </Card>
      {created && (
        <Card style={{ marginTop: 16 }}>
          <Typography.Title level={5}>新客户端 Token</Typography.Title>
          <Typography.Paragraph copyable>{created.token}</Typography.Paragraph>
        </Card>
      )}
      <Drawer title="新增客户端" open={open} onClose={() => setOpen(false)} width={420}>
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item label="客户端名称" name="name" rules={[{ required: true }]}>
            <Input placeholder="win-node-01" />
          </Form.Item>
          <Form.Item label="备注" name="remark">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit">创建</Button>
            <Button onClick={() => setOpen(false)}>取消</Button>
          </Space>
        </Form>
      </Drawer>
    </div>
  );
}
