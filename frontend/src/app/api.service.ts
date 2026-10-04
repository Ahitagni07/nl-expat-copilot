import {
  HttpClient,
} from '@angular/common/http';
import {
  Injectable,
} from '@angular/core';
import {
  Observable,
} from 'rxjs';

import {
  AnalyzeResponse,
  DeadlineListResponse,
  HealthResponse,
} from './models';


@Injectable({
  providedIn: 'root',
})
export class ApiService {
  constructor(
    private readonly http: HttpClient,
  ) {}

  health(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(
      '/api/health',
    );
  }

  analyze(
    file: File,
    instruction: string,
  ): Observable<AnalyzeResponse> {
    const data = new FormData();

    data.append('file', file);
    data.append(
      'instruction',
      instruction,
    );

    return this.http.post<AnalyzeResponse>(
      '/api/analyze',
      data,
    );
  }

  deadlines(): Observable<DeadlineListResponse> {
    return this.http.get<DeadlineListResponse>(
      '/api/deadlines',
    );
  }

  deadlineAnalysis(
    deadlineId: number,
  ): Observable<AnalyzeResponse> {
    return this.http.get<AnalyzeResponse>(
      `/api/deadlines/${deadlineId}/analysis`,
    );
  }

  deleteDeadline(
    deadlineId: number,
  ): Observable<{
    deleted: boolean;
    deadline_id: number;
  }> {
    return this.http.delete<{
      deleted: boolean;
      deadline_id: number;
    }>(
      `/api/deadlines/${deadlineId}`,
    );
  }
}
