// src/app/repositorio/repositorio.component.ts
import { Component, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../environments/environment';
import { ESPECIALIDADES } from '../core/services/laudo.service';
import { AuthService } from '../core/auth/auth.service';

interface UploadJob {
  id: string; name: string; status: 'uploading' | 'processing' | 'ready' | 'error';
  progress: number; error?: string;
}

@Component({
  selector: 'app-repositorio',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="repo-page">
      <div class="page-header">
        <h1>📚 Repositório de Referência</h1>
        <p>Adicione laudos reais para melhorar a qualidade das gerações futuras.</p>
      </div>

      <!-- Permissão -->
      <div class="access-notice" *ngIf="!isAdmin()">
        <span>🔒</span>
        <div>
          <strong>Acesso restrito</strong>
          <p>Apenas administradores podem adicionar laudos ao repositório. Contate o gestor do sistema.</p>
        </div>
      </div>

      <!-- Upload (admin apenas) -->
      <div *ngIf="isAdmin()">
        <div class="upload-config">
          <div class="field">
            <label>Especialidade dos laudos</label>
            <select [(ngModel)]="especialidade" class="select-input">
              <option value="">Selecione...</option>
              <option *ngFor="let e of especialidades" [value]="e">{{ e }}</option>
            </select>
          </div>
          <div class="field">
            <label>Tipo de Laudo <span class="opt">(opcional)</span></label>
            <input [(ngModel)]="tipoLaudo" placeholder="Ex: RX Tórax, TC Abdome..." class="text-input" />
          </div>
        </div>

        <div class="drop-zone"
             [class.dragging]="isDragging()"
             [class.disabled]="!especialidade"
             (dragover)="$event.preventDefault(); isDragging.set(true)"
             (dragleave)="isDragging.set(false)"
             (drop)="onDrop($event)">
          <div class="drop-content">
            <span class="drop-icon">📄</span>
            <p>Arraste laudos em PDF ou DOCX</p>
            <span class="drop-hint">Quanto mais laudos, melhor a qualidade das referências</span>
            <label class="btn-browse" [class.disabled]="!especialidade">
              Selecionar arquivos
              <input type="file" multiple accept=".pdf,.docx,.txt"
                     [disabled]="!especialidade"
                     (change)="onSelect($event)" hidden />
            </label>
          </div>
        </div>

        <p class="hint" *ngIf="!especialidade">⚠️ Selecione a especialidade antes de fazer upload</p>

        <!-- Jobs -->
        <div class="job-list" *ngIf="jobs().length > 0">
          <div *ngFor="let job of jobs()" class="job-item" [class]="job.status">
            <span class="job-icon">{{ statusIcon(job.status) }}</span>
            <div class="job-info">
              <span class="job-name">{{ job.name }}</span>
            </div>
            <div class="job-status">
              <div *ngIf="job.status === 'uploading'" class="progress-bar">
                <div class="progress-fill" [style.width.%]="job.progress"></div>
              </div>
              <span *ngIf="job.status === 'processing'" class="status-txt processing">Indexando...</span>
              <span *ngIf="job.status === 'ready'"      class="status-txt ready">✅ Indexado</span>
              <span *ngIf="job.status === 'error'"      class="status-txt error">❌ {{ job.error }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Info -->
      <div class="info-box">
        <h3>Como funciona o repositório?</h3>
        <ul>
          <li>Laudos adicionados aqui servem como <strong>referência</strong> para o Laudifier.</li>
          <li>Quando um médico gera um laudo, o sistema busca referências similares e as usa como base.</li>
          <li>Quanto mais laudos de qualidade no repositório, mais precisas são as gerações.</li>
          <li>Laudos aprovados pelos médicos também são adicionados automaticamente ao repositório.</li>
        </ul>
        <div class="stats" *ngIf="stats()">
          <div class="stat"><strong>{{ stats().total }}</strong><span>Laudos indexados</span></div>
          <div class="stat"><strong>{{ stats().especialidades }}</strong><span>Especialidades</span></div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .repo-page { padding: 24px; height: 100%; overflow-y: auto; max-width: 800px; margin: 0 auto; }
    .page-header h1 { font-size: 22px; font-weight: 700; color: var(--colorNeutralForeground1); margin: 0 0 4px; }
    .page-header p  { font-size: 14px; color: var(--colorNeutralForeground3); margin: 0 0 24px; }
    .access-notice { display: flex; gap: 14px; align-items: flex-start; padding: 16px; background: #fef3c7; border: 1px solid #fde68a; border-radius: 10px; margin-bottom: 24px; font-size: 14px; }
    .access-notice span { font-size: 24px; flex-shrink: 0; }
    .access-notice strong { display: block; margin-bottom: 4px; }
    .access-notice p { margin: 0; color: #92400e; font-size: 13px; }
    .upload-config { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
    .field { display: flex; flex-direction: column; gap: 6px; }
    .field label { font-size: 13px; font-weight: 600; color: var(--colorNeutralForeground2); }
    .opt { font-weight: 400; color: var(--colorNeutralForeground3); }
    .select-input, .text-input { padding: 9px 14px; border: 1px solid var(--colorNeutralStroke1); border-radius: 8px; font-size: 14px; background: var(--colorNeutralBackground2); color: var(--colorNeutralForeground1); outline: none; }
    .drop-zone { border: 2px dashed var(--colorNeutralStroke1); border-radius: 12px; padding: 40px 24px; text-align: center; cursor: pointer; transition: all 0.2s; }
    .drop-zone.dragging { border-color: var(--colorBrandStroke1); background: var(--colorBrandBackground2); }
    .drop-zone.disabled { opacity: 0.5; pointer-events: none; }
    .drop-content { display: flex; flex-direction: column; align-items: center; gap: 8px; }
    .drop-icon { font-size: 40px; }
    .drop-content p { font-size: 16px; font-weight: 500; color: var(--colorNeutralForeground1); margin: 0; }
    .drop-hint { font-size: 12px; color: var(--colorNeutralForeground3); }
    .btn-browse { padding: 8px 20px; background: var(--colorBrandBackground); color: white; border-radius: 6px; cursor: pointer; font-size: 14px; margin-top: 8px; }
    .btn-browse.disabled { opacity: 0.5; cursor: not-allowed; }
    .hint { font-size: 12px; color: #d97706; margin-top: 8px; }
    .job-list { display: flex; flex-direction: column; gap: 8px; margin-top: 16px; }
    .job-item { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border: 1px solid var(--colorNeutralStroke2); border-radius: 8px; background: var(--colorNeutralBackground2); }
    .job-icon { font-size: 20px; flex-shrink: 0; }
    .job-info { flex: 1; font-size: 14px; font-weight: 500; color: var(--colorNeutralForeground1); }
    .job-status { min-width: 160px; }
    .progress-bar { height: 6px; background: var(--colorNeutralBackground4); border-radius: 3px; overflow: hidden; }
    .progress-fill { height: 100%; background: var(--colorBrandBackground); border-radius: 3px; transition: width 0.3s; }
    .status-txt { font-size: 13px; }
    .status-txt.processing { color: var(--colorBrandForeground1); }
    .status-txt.ready  { color: #059669; }
    .status-txt.error  { color: #dc2626; }
    .info-box { margin-top: 32px; padding: 20px; background: var(--colorNeutralBackground2); border: 1px solid var(--colorNeutralStroke2); border-radius: 12px; }
    .info-box h3 { font-size: 15px; font-weight: 700; color: var(--colorNeutralForeground1); margin: 0 0 12px; }
    .info-box ul { margin: 0 0 16px; padding-left: 20px; }
    .info-box li { font-size: 14px; color: var(--colorNeutralForeground2); margin-bottom: 6px; }
    .stats { display: flex; gap: 24px; }
    .stat { display: flex; flex-direction: column; align-items: center; }
    .stat strong { font-size: 28px; font-weight: 700; color: var(--colorBrandForeground1); }
    .stat span   { font-size: 12px; color: var(--colorNeutralForeground3); }
  `],
})
export class RepositorioComponent {
  private http = inject(HttpClient);
  private auth = inject(AuthService);

  especialidades = ESPECIALIDADES;
  especialidade  = '';
  tipoLaudo      = '';
  isDragging     = signal(false);
  jobs           = signal<UploadJob[]>([]);
  stats          = signal<any>(null);

  isAdmin() { return this.auth.profile()?.role === 'admin'; }

  onDrop(e: DragEvent) {
    e.preventDefault();
    this.isDragging.set(false);
    const files = e.dataTransfer?.files;
    if (files) this.processFiles(files);
  }

  onSelect(e: Event) {
    const files = (e.target as HTMLInputElement).files;
    if (files) this.processFiles(files);
  }

  private processFiles(files: FileList) {
    Array.from(files).forEach(file => {
      const job: UploadJob = { id: crypto.randomUUID(), name: file.name, status: 'uploading', progress: 0 };
      this.jobs.update(j => [...j, job]);
      this.upload(file, job.id);
    });
  }

  private upload(file: File, jobId: string) {
    const form = new FormData();
    form.append('arquivo', file);
    form.append('especialidade', this.especialidade);
    form.append('tipo_laudo', this.tipoLaudo);

    this.http.post<{ job_id: string }>(`${environment.apiUrl}/repositorio/upload`, form, {
      reportProgress: true, observe: 'events',
    }).subscribe({
      next: evt => {
        if ((evt as any).type === 1) { // UploadProgress
          const pct = Math.round(100 * ((evt as any).loaded / ((evt as any).total ?? 1)));
          this.updateJob(jobId, { progress: pct });
        }
        if ((evt as any).type === 4) { // Response
          this.updateJob(jobId, { status: 'processing', progress: 100 });
          this.pollStatus(jobId, (evt as any).body.job_id);
        }
      },
      error: () => this.updateJob(jobId, { status: 'error', error: 'Falha no upload' }),
    });
  }

  private pollStatus(uiId: string, serverId: string) {
    const timer = setInterval(() => {
      this.http.get<{ status: string }>(`${environment.apiUrl}/ingest/status/${serverId}`)
        .subscribe(r => {
          if (r.status === 'ready') { this.updateJob(uiId, { status: 'ready' }); clearInterval(timer); }
          if (r.status === 'error') { this.updateJob(uiId, { status: 'error' }); clearInterval(timer); }
        });
    }, 3000);
  }

  private updateJob(id: string, patch: Partial<UploadJob>) {
    this.jobs.update(js => js.map(j => j.id === id ? { ...j, ...patch } : j));
  }

  statusIcon(s: string) {
    return ({ uploading: '⬆️', processing: '⚙️', ready: '✅', error: '❌' } as any)[s] ?? '📄';
  }
}
