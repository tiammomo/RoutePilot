/**
 * Fixed runtime settings component.
 */
import React from 'react';
import { useCLI } from '@/hooks/useCLI';

interface AIAssistantSettingsProps {
  projectId: string;
}

export function AIAssistantSettings({ projectId }: AIAssistantSettingsProps) {
  const { cliOptions, preference } = useCLI({ projectId });

  const selectedCLIOption = cliOptions.find(opt => opt.id === preference?.preferredCli);
  
  // Get the actual model name from preference data
  const getModelDisplayName = () => {
    if (!preference?.selectedModel) return 'Default Model';
    
    // Find the model name from the CLI options
    const currentCLI = selectedCLIOption;
    if (currentCLI?.models) {
      const model = currentCLI.models.find(m => m.id === preference.selectedModel);
      return model?.name || preference.selectedModel;
    }
    
    return preference.selectedModel;
  };
  
  const modelDisplayName = getModelDisplayName();

  return (
    <div className="p-6 space-y-6">
      <div>
        <h3 className="text-lg font-medium text-slate-900 mb-4">
          固定运行时
        </h3>
        
        <div className="space-y-4">
          {/* Current CLI */}
          <div className="p-4 bg-slate-50 rounded-lg">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-sm font-medium text-slate-700 mb-1">
                  运行时
                </h4>
                <div className="flex items-center gap-2">
                  <span className="text-lg font-semibold text-slate-900 ">
                    {selectedCLIOption?.name || preference?.preferredCli || 'Claude Code'}
                  </span>
                  {selectedCLIOption?.configured ? (
                    <span className="text-xs px-2 py-1 bg-green-100 text-green-700 rounded">
                      已配置
                    </span>
                  ) : (
                    <span className="text-xs px-2 py-1 bg-yellow-100 text-yellow-700 rounded">
                      未检测到配置
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Current Model */}
          <div className="p-4 bg-slate-50 rounded-lg">
            <h4 className="text-sm font-medium text-slate-700 mb-1">
              模型
            </h4>
            <span className="text-lg font-semibold text-slate-900 ">
              {modelDisplayName}
            </span>
          </div>


          {/* Note */}
          <div className="text-center">
            <p className="text-sm text-slate-500 ">
              项目固定使用 Claude Code runtime 与 mimo-v2.5-pro，界面不提供 CLI 或模型切换入口。
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
