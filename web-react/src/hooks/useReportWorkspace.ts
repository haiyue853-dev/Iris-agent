import { useReportChat } from './useReportChat';
import type { DailyReport } from '../types';

type Props = {
  report: DailyReport | null;
  onReportUpdated: (report: DailyReport) => void;
  onError: (message: string) => void;
};

export function useReportWorkspace(props: Props) {
  return {
    ...useReportChat(props),
    ready: props.report !== null,
  };
}

