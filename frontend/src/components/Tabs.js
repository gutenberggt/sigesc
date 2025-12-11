import { useState } from 'react';

export const Tabs = ({ tabs, defaultTab = 0, children }) => {
  const [activeTab, setActiveTab] = useState(defaultTab);

  return (
    <div className="w-full">
      {/* Tab Headers */}
      <div className="border-b border-gray-200">
        <nav className="flex space-x-4 overflow-x-auto" aria-label="Tabs">
          {tabs.map((tab, index) => (
            <button
              key={index}
              type="button"
              onClick={() => setActiveTab(index)}
              className={`
                py-3 px-4 text-sm font-medium whitespace-nowrap transition-colors
                ${
                  activeTab === index
                    ? 'border-b-2 border-blue-600 text-blue-600'
                    : 'text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }
              `}
              data-testid={`tab-${index}`}
            >
              {tab}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="mt-6">
        {typeof children === 'function' ? children(activeTab) : children[activeTab]}
      </div>
    </div>
  );
};
