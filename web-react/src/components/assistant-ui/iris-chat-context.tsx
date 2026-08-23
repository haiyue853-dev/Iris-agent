import { createContext, useContext } from "react";

export type IrisChatContextValue = {
  resolveApproval: (callId: string, approved: boolean) => Promise<void>;
};

export const IrisChatContext = createContext<IrisChatContextValue | null>(null);

export function useIrisChat(): IrisChatContextValue {
  const ctx = useContext(IrisChatContext);
  if (!ctx) throw new Error("useIrisChat must be used within an IrisChatContext.Provider");
  return ctx;
}
