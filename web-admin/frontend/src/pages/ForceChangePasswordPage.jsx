import React, { useState } from 'react';
import { LockOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { Button, Card, Form, Input, Typography, message } from 'antd';
import { BrandLockup } from '../components/BrandLogo';
import { changePassword } from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function ForceChangePasswordPage() {
  const [loading, setLoading] = useState(false);
  const { refreshUser } = useAuth();

  const handleFinish = async (values) => {
    setLoading(true);
    try {
      await changePassword({
        current_password: values.current_password,
        new_password: values.new_password,
      });
      const user = await refreshUser();
      message.success('密码已更新，请继续使用后台');
      window.location.href = user?.must_change_password ? '/force-change-password' : '/';
    } catch (error) {
      message.error(error?.response?.data?.detail || '修改密码失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-shell">
      <div className="login-shell__panel">
        <div className="login-shell__intro">
          <BrandLockup
            size="xl"
            title="GitHub Asset Center"
            subtitle="首次登录安全校验，完成管理员密码更新后再进入后台"
          />
          <span className="login-shell__eyebrow">Security Update</span>
          <Typography.Title level={2}>请先修改默认密码</Typography.Title>
          <Typography.Paragraph>
            当前登录使用的是系统默认管理员密码。为继续访问资产后台，必须先设置一个新的安全密码。
          </Typography.Paragraph>
        </div>
        <Card className="login-card">
          <div className="login-card__badge">
            <SafetyCertificateOutlined />
            <span>强制改密</span>
          </div>
          <Typography.Title level={3}>更新管理员密码</Typography.Title>
          <Typography.Paragraph>
            新密码至少 8 位，且不能继续使用默认密码。
          </Typography.Paragraph>
          <Form layout="vertical" onFinish={handleFinish}>
            <Form.Item label="当前密码" name="current_password" rules={[{ required: true }]}>
              <Input.Password prefix={<LockOutlined />} placeholder="请输入当前密码" />
            </Form.Item>
            <Form.Item
              label="新密码"
              name="new_password"
              rules={[
                { required: true },
                { min: 8, message: '新密码至少 8 位' },
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="请输入新密码" />
            </Form.Item>
            <Form.Item
              label="确认新密码"
              name="confirm_password"
              dependencies={['new_password']}
              rules={[
                { required: true },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('new_password') === value) {
                      return Promise.resolve();
                    }
                    return Promise.reject(new Error('两次输入的新密码不一致'));
                  },
                }),
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="请再次输入新密码" />
            </Form.Item>
            <Button type="primary" htmlType="submit" block size="large" loading={loading}>
              更新密码并进入后台
            </Button>
          </Form>
        </Card>
      </div>
    </div>
  );
}
