// src/app/core/services/memory.service.ts
import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface Memoria {
  id:         string;
  conteudo:   string;
  categorias: string[];
  criada_em:  string;
  score?:     number;
}

export interface MemoriasResponse {
  total:    number;
  memorias: Memoria[];
}

export interface PreviewContexto {
  especialidade: string;
  contexto:      string;
  tem_contexto:  boolean;
}

@Injectable({ providedIn: 'root' })
export class MemoryService {
  private http = inject(HttpClient);
  private base = `${environment.apiUrl}/memoria`;

  listar(): Observable<MemoriasResponse> {
    return this.http.get<MemoriasResponse>(this.base);
  }

  deletar(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }

  limparTodas(): Observable<void> {
    return this.http.delete<void>(this.base);
  }

  previewContexto(especialidade: string, solicitacao?: string): Observable<PreviewContexto> {
    const params: any = { especialidade };
    if (solicitacao) params['solicitacao'] = solicitacao;
    return this.http.get<PreviewContexto>(`${this.base}/preview`, { params });
  }
}


// ─────────────────────────────────────────────────────────────────────────────
// src/app/memorias/memorias.component.ts
// ─────────────────────────────────────────────────────────────────────────────

import { Component, OnInit, signal, inject as inj } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MemoryService, Memoria } from '../core/services/memory.service';
import { ESPECIALIDADES } from '../core/services/laudo.service';

@Component({
  selector: 'app-memorias',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="mem-page">
      <div class="page-header">
        <div>
          <h1>💾 Memória Personalizada</h1>
          <p>O Laudifier aprende com cada laudo gerado e aplica essas preferências automaticamente.</p>
        </div>
        <div class="header-actions" *ngIf="memorias().length > 0">
          <button class="btn-danger" (click)="confirmarLimpar()">🗑️ Limpar tudo</button>
        </div>
      </div>

      <!-- Prévia de contexto -->
      <div class="preview-card">
        <h2 class="section-title">🔍 Prévia do contexto para o próximo laudo</h2>
        <div class="preview-controls">
          <select [(ngModel)]="espPreview" (change)="carregarPreview()" class="select-sm">
            <option value="">Selecione especialidade...</option>
            <option *ngFor="let e of especialidades" [value]="e">{{ e }}</option>
          </select>
        </div>
        <div class="preview-content" *ngIf="preview()">
          <div *ngIf="preview()!.tem_contexto" class="preview-text">
            <span class="badge-mem">Ativo</span>
            <pre>{{ preview()!.contexto }}</pre>
          </div>
          <div *ngIf="!preview()!.tem_contexto" class="preview-empty">
            Nenhuma memória relevante para esta especialidade ainda.
            Gere alguns laudos para o Laudifier aprender suas preferências.
          </div>
        </div>
      </div>

      <!-- Loading -->
      <div *ngIf="loading()" class="skeleton-list">
        <div class="skeleton-row" *ngFor="let i of [1,2,3]"></div>
      </div>

      <!-- Empty -->
      <div *ngIf="!loading() && memorias().length === 0" class="empty-state">
        <span class="empty-icon">🧠</span>
        <h3>Nenhuma memória ainda</h3>
        <p>O Laudifier começa a aprender automaticamente após os primeiros laudos gerados. Quanto mais você usar, mais personalizado fica.</p>
      </div>

      <!-- Lista de memórias -->
      <div *ngIf="!loading() && memorias().length > 0">
        <h2 class="section-title">
          O que o Laudifier aprendeu sobre você
          <span class="count-badge">{{ memorias().length }}</span>
        </h2>
        <div class="mem-list">
          <div *ngFor="let mem of memorias()" class="mem-card">
            <div class="mem-body">
              <p class="mem-text">{{ mem.conteudo }}</p>
              <div class="mem-meta">
                <span *ngFor="let cat of mem.categorias" class="cat-tag">{{ cat }}</span>
                <span class="mem-date">{{ mem.criada_em | date:'dd/MM/yy' }}</span>
              </div>
            </div>
            <button class="btn-delete" (click)="deletar(mem.id)" title="Esquecer esta memória">
              ✕
            </button>
          </div>
        </div>
      </div>

      <!-- Info -->
      <div class="info-box">
        <h3>Como funciona o Mem0?</h3>
        <ul>
          <li>Após cada laudo gerado, o sistema extrai automaticamente fatos relevantes — como seu estilo de escrita, nível de detalhe preferido e terminologia usada.</li>
          <li>Quando você corrige um laudo, o sistema aprende com a diferença entre o original e sua versão editada.</li>
          <li>Nas próximas gerações, esse contexto é injetado automaticamente no prompt, tornando os laudos cada vez mais alinhados com seu padrão.</li>
          <li>Você tem controle total: pode ver, remover memórias individuais ou limpar tudo.</li>
        </ul>
      </div>
    </div>
  `,
  styles: [`
    .mem-page { padding: 24px; height: 100%; overflow-y: auto; max-width: 860px; margin: 0 auto; display: flex; flex-direction: column; gap: 24px; }
    .page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
    .page-header h1 { font-size: 22px; font-weight: 700; color: var(--colorNeutralForeground1); margin: 0 0 4px; }
    .page-header p  { font-size: 14px; color: var(--colorNeutralForeground3); margin: 0; }
    .btn-danger { padding: 8px 16px; background: #fef2f2; border: 1px solid #fca5a5; color: #dc2626; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }
    .btn-danger:hover { background: #fee2e2; }

    .preview-card { background: var(--colorNeutralBackground2); border: 1px solid var(--colorNeutralStroke2); border-radius: 12px; padding: 20px; }
    .section-title { font-size: 16px; font-weight: 600; color: var(--colorNeutralForeground1); margin: 0 0 14px; display: flex; align-items: center; gap: 8px; }
    .count-badge { background: var(--colorBrandBackground2); color: var(--colorBrandForeground1); font-size: 12px; padding: 2px 8px; border-radius: 10px; font-weight: 700; }
    .preview-controls { margin-bottom: 12px; }
    .select-sm { padding: 7px 12px; border: 1px solid var(--colorNeutralStroke1); border-radius: 6px; font-size: 13px; background: var(--colorNeutralBackground1); color: var(--colorNeutralForeground1); outline: none; }
    .preview-content { background: var(--colorNeutralBackground1); border-radius: 8px; padding: 14px; }
    .badge-mem { background: #d1fae5; color: #065f46; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 10px; display: inline-block; margin-bottom: 8px; }
    .preview-text pre { margin: 0; font-family: inherit; font-size: 13px; color: var(--colorNeutralForeground2); white-space: pre-wrap; line-height: 1.6; }
    .preview-empty { font-size: 13px; color: var(--colorNeutralForeground3); font-style: italic; }

    .skeleton-list { display: flex; flex-direction: column; gap: 8px; }
    .skeleton-row { height: 80px; border-radius: 8px; background: var(--colorNeutralBackground3); animation: shimmer 1.4s infinite; }
    @keyframes shimmer { 0%,100%{opacity:1} 50%{opacity:0.5} }

    .empty-state { text-align: center; padding: 48px; }
    .empty-icon { font-size: 48px; display: block; margin-bottom: 12px; }
    .empty-state h3 { font-size: 18px; font-weight: 600; color: var(--colorNeutralForeground1); margin: 0 0 8px; }
    .empty-state p  { font-size: 14px; color: var(--colorNeutralForeground3); max-width: 400px; margin: 0 auto; line-height: 1.6; }

    .mem-list { display: flex; flex-direction: column; gap: 8px; }
    .mem-card { display: flex; align-items: flex-start; gap: 12px; padding: 14px 16px; border: 1px solid var(--colorNeutralStroke2); border-radius: 8px; background: var(--colorNeutralBackground2); transition: all 0.13s; }
    .mem-card:hover { border-color: var(--colorNeutralStroke1); }
    .mem-body { flex: 1; }
    .mem-text { font-size: 14px; color: var(--colorNeutralForeground1); margin: 0 0 8px; line-height: 1.5; }
    .mem-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .cat-tag { background: var(--colorBrandBackground2); color: var(--colorBrandForeground1); font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 10px; }
    .mem-date { font-size: 11px; color: var(--colorNeutralForeground4); margin-left: auto; }
    .btn-delete { background: none; border: none; color: var(--colorNeutralForeground4); cursor: pointer; font-size: 14px; padding: 4px 8px; border-radius: 4px; flex-shrink: 0; }
    .btn-delete:hover { background: #fef2f2; color: #dc2626; }

    .info-box { padding: 20px; background: var(--colorNeutralBackground2); border: 1px solid var(--colorNeutralStroke2); border-radius: 12px; }
    .info-box h3 { font-size: 15px; font-weight: 700; color: var(--colorNeutralForeground1); margin: 0 0 12px; }
    .info-box ul { margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 8px; }
    .info-box li { font-size: 13px; color: var(--colorNeutralForeground2); line-height: 1.6; }
  `],
})
export class MemoriasComponent implements OnInit {
  private memSvc = inj(MemoryService);

  memorias    = signal<Memoria[]>([]);
  loading     = signal(true);
  preview     = signal<any>(null);
  espPreview  = '';
  especialidades = ESPECIALIDADES;

  ngOnInit() {
    this.memSvc.listar().subscribe({
      next:  r  => { this.memorias.set(r.memorias); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  carregarPreview() {
    if (!this.espPreview) return;
    this.memSvc.previewContexto(this.espPreview).subscribe(r => this.preview.set(r));
  }

  deletar(id: string) {
    this.memSvc.deletar(id).subscribe(() =>
      this.memorias.update(m => m.filter(x => x.id !== id))
    );
  }

  confirmarLimpar() {
    if (!confirm('Remover TODAS as memórias? O Laudifier começará a aprender do zero.')) return;
    this.memSvc.limparTodas().subscribe(() => this.memorias.set([]));
  }
}
