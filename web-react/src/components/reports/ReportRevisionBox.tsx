import { useState } from 'react';

type Props = {
  disabled: boolean;
  revising: boolean;
  onRevise: (instruction: string) => void;
};

export default function ReportRevisionBox({ disabled, revising, onRevise }: Props) {
  const [instruction, setInstruction] = useState('');

  const submit = () => {
    const value = instruction.trim();
    if (!value || disabled) return;
    onRevise(value);
    setInstruction('');
  };

  return (
    <div className="report-revision-box">
      <label htmlFor="report-revision">AI 修改要求</label>
      <div>
        <input
          id="report-revision"
          value={instruction}
          maxLength={2_000}
          disabled={disabled}
          placeholder="例如：更简短，突出成果"
          onChange={(event) => setInstruction(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') submit();
          }}
        />
        <button disabled={disabled || !instruction.trim()} onClick={submit}>
          {revising ? '修改中…' : 'AI 修改'}
        </button>
      </div>
    </div>
  );
}
