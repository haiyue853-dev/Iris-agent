import React from 'react';
import InputBox from './InputBox';

interface WelcomePageProps {
  inputValue: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
}

const WelcomePage: React.FC<WelcomePageProps> = ({
  inputValue,
  onInputChange,
  onSend,
}) => {
  return (
    <div className="welcome-container">
      <div className="welcome-logo">IRIS</div>
      <div className="input-wrapper">
        <InputBox
          value={inputValue}
          onChange={onInputChange}
          onSend={onSend}
          placeholder="输入 '/' 唤起插件和技能"
          autoFocus={true}
        />
      </div>
    </div>
  );
};

export default WelcomePage;
