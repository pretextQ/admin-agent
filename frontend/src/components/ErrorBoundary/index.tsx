import { Component, type ReactNode } from "react";
import { Button } from "@douyinfe/semi-ui";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ textAlign: "center", padding: 80 }}>
          <h3>页面出错了</h3>
          <p style={{ color: "#999", marginBottom: 16 }}>
            {this.state.error?.message}
          </p>
          <Button
            onClick={() => {
              this.setState({ hasError: false, error: null });
              window.location.href = "/";
            }}
          >
            重新加载
          </Button>
        </div>
      );
    }
    return this.props.children;
  }
}
