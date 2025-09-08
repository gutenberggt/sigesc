import React from "react";
import { PageHeader } from "./pageHeader";

export function PageLayout({ title, subtitle, actions, tabs, children }) {
  return (
    <div className="p-6 relative">
      <PageHeader title={title} subtitle={subtitle} actions={actions} />

      {tabs ? (
        <div className="mt-4">{tabs}</div>
      ) : (
        <div className="mt-4">{children}</div>
      )}
    </div>
  );
}
