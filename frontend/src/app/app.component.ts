import {
  ChangeDetectionStrategy,
  Component,
  OnDestroy,
  OnInit,
  computed,
  signal,
} from '@angular/core';
import {
  finalize,
} from 'rxjs';

import {
  ApiService,
} from './api.service';
import {
  AnalyzeResponse,
  DeadlineAction,
} from './models';


type BackendState =
  | 'checking'
  | 'ready'
  | 'offline';


@Component({
  selector: 'app-root',
  standalone: true,
  imports: [],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css',
  changeDetection:
    ChangeDetectionStrategy.OnPush,
})
export class AppComponent
  implements OnInit, OnDestroy
{
  readonly file = signal<File | null>(null);
  readonly previewUrl =
    signal<string | null>(null);

  readonly dragging = signal(false);
  readonly running = signal(false);

  readonly result =
    signal<AnalyzeResponse | null>(null);

  readonly error = signal('');

  readonly backendState =
    signal<BackendState>('checking');

  readonly model = signal('');

  readonly deadlines =
    signal<DeadlineAction[]>([]);

  readonly viewingSavedDeadlineId =
    signal<number | null>(null);

  readonly loadingDeadlineId =
    signal<number | null>(null);

  readonly deadlineMessage = signal('');

  readonly pendingDeleteDeadline =
    signal<DeadlineAction | null>(null);

  readonly deletingDeadlineId =
    signal<number | null>(null);

  private readonly analysisInstruction =
    'Explain this Dutch letter to me as an expat. ' +
    'Tell me what it is, whether I can ignore it, ' +
    'exactly what I need to do and by when. ' +
    'Use official-process guidance where useful, ' +
    'and prepare only the actions that actually make sense.';

  readonly canAnalyze = computed(
    () =>
      this.file() !== null &&
      !this.running() &&
      this.backendState() === 'ready',
  );

  readonly visibleDeadlines = computed(
    () => this.deadlines().slice(0, 6),
  );

  constructor(
    private readonly api: ApiService,
  ) {}

  ngOnInit(): void {
    this.checkBackend();
    this.loadDeadlines();
  }

  ngOnDestroy(): void {
    this.revokePreviewUrl();
  }

  checkBackend(): void {
    this.backendState.set('checking');

    this.api.health().subscribe({
      next: (health) => {
        this.model.set(health.model);

        if (
          health.api_key_configured === false
        ) {
          this.backendState.set('offline');
          this.error.set(
            'FastAPI is running, but ' +
            'OPENROUTER_API_KEY is not configured ' +
            'in backend/.env.',
          );
          return;
        }

        this.backendState.set('ready');
      },
      error: () =>
        this.backendState.set('offline'),
    });
  }

  onFileInput(event: Event): void {
    const input =
      event.target as HTMLInputElement;

    const selected =
      input.files?.[0];

    if (selected) {
      this.setFile(selected);
    }

    input.value = '';
  }

  onDragOver(
    event: DragEvent,
  ): void {
    event.preventDefault();
    event.stopPropagation();
    this.dragging.set(true);
  }

  onDragLeave(
    event: DragEvent,
  ): void {
    event.preventDefault();
    event.stopPropagation();
    this.dragging.set(false);
  }

  onDrop(
    event: DragEvent,
  ): void {
    event.preventDefault();
    event.stopPropagation();
    this.dragging.set(false);

    const selected =
      event.dataTransfer?.files?.[0];

    if (selected) {
      this.setFile(selected);
    }
  }

  clearFile(): void {
    this.revokePreviewUrl();
    this.file.set(null);
    this.previewUrl.set(null);
    this.result.set(null);
    this.viewingSavedDeadlineId.set(null);
    this.error.set('');
  }

  analyze(): void {
    const selected = this.file();

    if (
      !selected ||
      !this.canAnalyze()
    ) {
      return;
    }

    this.running.set(true);
    this.result.set(null);
    this.error.set('');
    this.deadlineMessage.set('');
    this.viewingSavedDeadlineId.set(null);

    this.api
      .analyze(
        selected,
        this.analysisInstruction,
      )
      .pipe(
        finalize(
          () => this.running.set(false),
        ),
      )
      .subscribe({
        next: (response) => {
          this.result.set(response);
          this.loadDeadlines();
          this.scrollToAnalysis();
        },

        error: (err: unknown) => {
          const httpError = err as {
            error?: {
              detail?: string;
            };
            message?: string;
          };

          this.error.set(
            httpError?.error?.detail ??
              httpError?.message ??
              (
                'Analysis failed. Check FastAPI, ' +
                'your OpenRouter API key and ' +
                'the configured model.'
              ),
          );
        },
      });
  }

  loadDeadlines(): void {
    this.api.deadlines().subscribe({
      next: (response) =>
        this.deadlines.set(
          response.deadlines,
        ),

      error: () =>
        this.deadlines.set([]),
    });
  }

  openDeadline(
    deadline: DeadlineAction,
  ): void {
    this.deadlineMessage.set('');

    if (!deadline.has_details) {
      this.deadlineMessage.set(
        'Detailed analysis is not available for ' +
        'this older saved item. Re-upload its ' +
        'original letter once; the app will link ' +
        'the full details to this deadline.',
      );
      return;
    }

    this.loadingDeadlineId.set(
      deadline.id,
    );
    this.error.set('');

    this.api
      .deadlineAnalysis(deadline.id)
      .pipe(
        finalize(
          () =>
            this.loadingDeadlineId.set(
              null,
            ),
        ),
      )
      .subscribe({
        next: (analysis) => {
          this.viewingSavedDeadlineId.set(
            deadline.id,
          );
          this.result.set(analysis);
          this.scrollToAnalysis();
        },

        error: (err: unknown) => {
          const httpError = err as {
            error?: {
              detail?: string;
            };
          };

          this.deadlineMessage.set(
            httpError?.error?.detail ??
              'Could not load the saved details.',
          );
        },
      });
  }

  requestDeleteDeadline(
    event: Event,
    deadline: DeadlineAction,
  ): void {
    event.stopPropagation();
    this.pendingDeleteDeadline.set(
      deadline,
    );
  }

  cancelDeleteDeadline(): void {
    if (this.deletingDeadlineId() !== null) {
      return;
    }

    this.pendingDeleteDeadline.set(null);
  }

  confirmDeleteDeadline(): void {
    const deadline =
      this.pendingDeleteDeadline();

    if (!deadline) {
      return;
    }

    this.deletingDeadlineId.set(
      deadline.id,
    );
    this.deadlineMessage.set('');

    this.api
      .deleteDeadline(deadline.id)
      .pipe(
        finalize(() =>
          this.deletingDeadlineId.set(null),
        ),
      )
      .subscribe({
        next: () => {
          this.pendingDeleteDeadline.set(null);

          if (
            this.viewingSavedDeadlineId() ===
            deadline.id
          ) {
            this.viewingSavedDeadlineId.set(null);
            this.result.set(null);
          }

          this.deadlines.update((items) =>
            items.filter(
              (item) => item.id !== deadline.id,
            ),
          );

          this.deadlineMessage.set(
            'Saved deadline removed.',
          );
        },

        error: (err: unknown) => {
          const httpError = err as {
            error?: { detail?: string };
          };

          this.deadlineMessage.set(
            httpError?.error?.detail ??
              'Could not remove the saved deadline.',
          );
        },
      });
  }

  formatDate(value: string): string {
    const parsed = new Date(value);

    if (
      Number.isNaN(parsed.getTime())
    ) {
      return value;
    }

    const options:
      Intl.DateTimeFormatOptions = {
        dateStyle: 'medium',
      };

    if (value.includes('T')) {
      options.timeStyle = 'short';
    }

    return new Intl.DateTimeFormat(
      undefined,
      options,
    ).format(parsed);
  }

  deadlineDay(value: string): string {
    const parsed = new Date(value);

    return Number.isNaN(
      parsed.getTime(),
    )
      ? '--'
      : new Intl.DateTimeFormat(
          undefined,
          {
            day: '2-digit',
          },
        ).format(parsed);
  }

  deadlineMonth(value: string): string {
    const parsed = new Date(value);

    return Number.isNaN(
      parsed.getTime(),
    )
      ? ''
      : new Intl.DateTimeFormat(
          undefined,
          {
            month: 'short',
          },
        )
          .format(parsed)
          .toUpperCase();
  }

  absoluteApiUrl(
    path: string,
  ): string {
    return path;
  }

  categoryLabel(
    category: string,
  ): string {
    const labels:
      Record<string, string> = {
        payment_required:
          'Payment required',
        appointment_or_visit:
          'Appointment / visit',
        action_required:
          'Action required',
        information_only:
          'Information only',
        mixed:
          'Multiple actions',
        needs_review:
          'Needs review',
      };

    return (
      labels[category] ??
      category
    );
  }

  categoryIcon(
    category: string,
  ): string {
    const icons:
      Record<string, string> = {
        payment_required: '€',
        appointment_or_visit: '▦',
        action_required: '!',
        information_only: 'i',
        mixed: '↗',
        needs_review: '?',
      };

    return (
      icons[category] ??
      '?'
    );
  }

  ignoreLabel(
    value: string,
  ): string {
    if (
      value === 'probably_yes'
    ) {
      return 'Probably yes';
    }

    if (value === 'no') {
      return 'No';
    }

    return 'Unclear';
  }

  private setFile(
    selected: File,
  ): void {
    const lowerName =
      selected.name.toLowerCase();

    const isPdf =
      selected.type ===
        'application/pdf' ||
      lowerName.endsWith('.pdf');

    const isImage =
      selected.type.startsWith(
        'image/',
      );

    if (
      !isImage &&
      !isPdf
    ) {
      this.error.set(
        'Please choose an image or PDF file.',
      );
      return;
    }

    const maximumBytes =
      isPdf
        ? 20 * 1024 * 1024
        : 12 * 1024 * 1024;

    if (
      selected.size >
      maximumBytes
    ) {
      this.error.set(
        isPdf
          ? (
              'PDF is too large. ' +
              'Keep it under 20 MB.'
            )
          : (
              'Image is too large. ' +
              'Keep it under 12 MB.'
            ),
      );
      return;
    }

    this.revokePreviewUrl();

    this.file.set(selected);
    this.result.set(null);
    this.viewingSavedDeadlineId.set(null);
    this.deadlineMessage.set('');
    this.error.set('');

    this.previewUrl.set(
      isImage
        ? URL.createObjectURL(
            selected,
          )
        : null,
    );
  }

  private revokePreviewUrl(): void {
    const current =
      this.previewUrl();

    if (current) {
      URL.revokeObjectURL(
        current,
      );
    }
  }

  private scrollToAnalysis(): void {
    setTimeout(() => {
      document
        .getElementById(
          'analysis-result',
        )
        ?.scrollIntoView({
          behavior: 'smooth',
          block: 'start',
        });
    });
  }
}
