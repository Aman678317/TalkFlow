import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios';
import { AppConfig, DesiCliError } from '../types/index.js';
import { VERSION, CLIENT_NAME } from '../version.js';

export class HttpClient {
  private client: AxiosInstance;
  private maxRetries: number;

  constructor(config: AppConfig) {
    this.maxRetries = config.maxRetries || 3;

    const headers: Record<string, string> = {
      'User-Agent': `${CLIENT_NAME}/${VERSION} (Node.js ${process.version})`,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    };

    if (config.apiKey) {
      headers['X-API-Key'] = config.apiKey;
      headers['Authorization'] = `Bearer ${config.apiKey}`;
      // DeepL-Auth-Key backwards compatibility header
      headers['DeepL-Auth-Key'] = config.apiKey;
    }

    this.client = axios.create({
      baseURL: config.apiUrl || 'https://api.globaltalk.ai',
      timeout: config.timeoutMs || 30000,
      headers,
    });
  }

  public async request<T = any>(reqConfig: AxiosRequestConfig): Promise<AxiosResponse<T>> {
    let attempt = 0;
    let delay = 1000;

    while (true) {
      attempt++;
      try {
        return await this.client.request<T>(reqConfig);
      } catch (err: any) {
        const status = err.response?.status;
        const responseData = err.response?.data;
        const errorMessage = responseData?.message || responseData?.error || err.message;

        // Exit Code 2: Unauthorized / Forbidden API Key
        if (status === 401) {
          throw new DesiCliError(
            'Authentication failed: Invalid or missing API key',
            2,
            'Run "desi init" or set DESI_API_KEY environment variable.'
          );
        }

        // Exit Code 4: Quota Exceeded
        if (status === 403 && (errorMessage.includes('quota') || errorMessage.includes('limit'))) {
          throw new DesiCliError(
            `Quota exceeded: ${errorMessage}`,
            4,
            'Check your character or document quota with "desi usage".'
          );
        }

        // Retryable: Rate limit (429) or Server unavailable (503 / 502 / ECONNRESET)
        const isRetryable =
          status === 429 ||
          status === 503 ||
          status === 502 ||
          err.code === 'ECONNRESET' ||
          err.code === 'ETIMEDOUT';

        if (isRetryable && attempt <= this.maxRetries) {
          const jitter = Math.random() * 200;
          const retryAfter = err.response?.headers?.['retry-after'];
          const waitTime = retryAfter ? parseInt(retryAfter, 10) * 1000 : delay + jitter;
          await new Promise((resolve) => setTimeout(resolve, waitTime));
          delay *= 2;
          continue;
        }

        // If rate limit persisted past max retries
        if (status === 429) {
          throw new DesiCliError(
            'Rate limit exceeded: Too many requests',
            3,
            'Reduce concurrency or retry after a moment.'
          );
        }

        // Network or server failure
        if (!status || status >= 500) {
          throw new DesiCliError(
            `Network error: ${errorMessage}`,
            5,
            'Verify your internet connection or check the API server status.'
          );
        }

        // Input validation error
        if (status === 400) {
          throw new DesiCliError(
            `Invalid input: ${errorMessage}`,
            6,
            'Check your arguments and language codes.'
          );
        }

        throw new DesiCliError(`API Error (${status || 'unknown'}): ${errorMessage}`, 1);
      }
    }
  }

  public async get<T = any>(url: string, config?: AxiosRequestConfig): Promise<AxiosResponse<T>> {
    return this.request<T>({ ...config, method: 'GET', url });
  }

  public async post<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<AxiosResponse<T>> {
    return this.request<T>({ ...config, method: 'POST', url, data });
  }

  public async delete<T = any>(url: string, config?: AxiosRequestConfig): Promise<AxiosResponse<T>> {
    return this.request<T>({ ...config, method: 'DELETE', url });
  }
}
