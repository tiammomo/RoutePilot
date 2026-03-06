import React from 'react';
import { Select, Spin, App } from 'antd';
import { RobotOutlined } from '@ant-design/icons';
import { useAppContext } from '../context/AppContext';
import { logger } from '../utils/logger';

const { Option } = Select;

const ModelSelector: React.FC = () => {
  const {
    availableModels,
    currentModelId,
    setCurrentModelId,
    loadingModels,
  } = useAppContext();

  // 使用 antd App 上下文获取 message 实例
  const { message } = App.useApp();

  const [switching, setSwitching] = React.useState(false);

  const handleChange = async (value: string) => {
    try {
      setSwitching(true);
      await setCurrentModelId(value);
      const model = availableModels.find(m => m.model_id === value);
      message.success(`已切换到 ${model?.name || value}`);
    } catch (error) {
      message.error('模型切换失败，请重试');
      logger.error('模型切换错误:', error);
    } finally {
      setSwitching(false);
    }
  };

  // 优化：默认模型已立即可用，不显示加载状态
  // 只有当没有默认模型且正在加载时才显示加载状态
  const hasDefaultModels = availableModels.length > 0 && availableModels.some(
    m => m.model_id === 'minimax-m2-5'
  );

  if (loadingModels && !hasDefaultModels) {
    return (
      <div style={{
        width: 200,
        height: 32,
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '4px 12px',
        border: '1px solid #d9d9d9',
        borderRadius: '6px'
      }}>
        <RobotOutlined style={{ color: '#1890ff' }} />
        <Spin size="small" />
        <span style={{ fontSize: '14px', color: '#999' }}>加载中...</span>
      </div>
    );
  }

  return (
    <Select
      value={currentModelId}
      onChange={handleChange}
      style={{ width: 200 }}
      placeholder="选择模型"
      suffixIcon={<RobotOutlined />}
      loading={switching}
      disabled={loadingModels || availableModels.length === 0 || switching}
    >
      {availableModels.map((model) => (
        <Option key={model.model_id} value={model.model_id}>
          {model.name}
        </Option>
      ))}
    </Select>
  );
};

export default ModelSelector;
