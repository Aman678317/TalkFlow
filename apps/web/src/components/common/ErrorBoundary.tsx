import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw, Home, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onReset?: () => void;
  title?: string;
  sectionName?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.setState({ errorInfo });
    // Structured error logging for observability
    console.error(`[ErrorBoundary${this.props.sectionName ? `:${this.props.sectionName}` : ""}]`, {
      message: error.message,
      name: error.name,
      stack: error.stack,
      componentStack: errorInfo.componentStack,
    });
  }

  handleReset = (): void => {
    this.props.onReset?.();
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  handleReload = (): void => {
    window.location.reload();
  };

  handleGoHome = (): void => {
    window.location.href = "/dashboard";
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      const isNetworkError =
        this.state.error?.message.toLowerCase().includes("network") ||
        this.state.error?.message.toLowerCase().includes("fetch") ||
        this.state.error?.message.toLowerCase().includes("timed out");

      return (
        <div
          role="alert"
          aria-live="assertive"
          className="flex min-h-[400px] w-full flex-1 flex-col items-center justify-center p-6 text-center select-none"
        >
          <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-8 shadow-xl shadow-slate-900/5 transition-all">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-50 text-rose-600 ring-8 ring-rose-50/50">
              {isNetworkError ? (
                <AlertTriangle className="h-7 w-7" aria-hidden="true" />
              ) : (
                <ShieldAlert className="h-7 w-7" aria-hidden="true" />
              )}
            </div>

            <h2 className="text-lg font-bold tracking-tight text-slate-900 sm:text-xl">
              {this.props.title || (isNetworkError ? "Connection Interrupted" : "Something Went Wrong")}
            </h2>

            <p className="mt-2 text-sm text-slate-600 leading-relaxed">
              {isNetworkError
                ? "We encountered a temporary connection issue. Your data and preferences are safe. Please check your connection or try again."
                : "An unexpected error occurred while rendering this view. Our telemetry system has logged this incident."}
            </p>

            {this.state.error?.message && (
              <div className="mt-4 overflow-hidden rounded-xl bg-slate-50 border border-slate-200 p-3 text-left">
                <p className="text-xs font-mono text-slate-700 break-words line-clamp-3">
                  {this.state.error.message}
                </p>
              </div>
            )}

            <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
              <Button
                variant="primary"
                onClick={this.handleReset}
                className="gap-2 text-xs font-semibold"
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                Try Again
              </Button>

              <Button
                variant="secondary"
                onClick={this.handleReload}
                className="gap-2 text-xs font-semibold"
              >
                Reload Page
              </Button>

              <Button
                variant="ghost"
                onClick={this.handleGoHome}
                className="gap-2 text-xs font-semibold text-slate-600 hover:text-slate-900"
              >
                <Home className="h-3.5 w-3.5" aria-hidden="true" />
                Dashboard
              </Button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
