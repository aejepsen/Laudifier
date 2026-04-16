// src/app/dashboard/dashboard.component.ts
import { Component, OnInit, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LaudoService } from '../core/services/laudo.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="dash-page">
      <h1 class="page-title">Dashboard</h1>

      <div *ngIf="loading()" class="kpi-grid">
        <div class="skeleton-kpi" *ngFor="let i of [1,2,3,4]"></div>
      </div>

      <ng-container *ngIf="!loading() && stats() as s">
        <!-- KPIs -->
        <div class="kpi-grid">
          <div class="kpi-card">
            <span class="kpi-accent">Laudos</span>
            <span class="kpi-val">{{ s.total_laudos }}</span>
            <span class="kpi-lbl">Gerados</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-accent">RAG</span>
            <span class="kpi-val">{{ s.por_rag }}</span>
            <span class="kpi-lbl">Do repositório</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-accent">LLM</span>
            <span class="kpi-val">{{ s.por_fallback }}</span>
            <span class="kpi-lbl">Pelo Claude</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-accent">Taxa</span>
            <span class="kpi-val" [class.kpi-val--good]="s.taxa_aprovacao >= 0.8" [class.kpi-val--warn]="s.taxa_aprovacao < 0.8">
              {{ (s.taxa_aprovacao * 100).toFixed(0) }}%
            </span>
            <span class="kpi-lbl">Aprovação</span>
          </div>
        </div>

        <!-- Por especialidade -->
        <div class="section" *ngIf="s.por_especialidade">
          <h2 class="section-title">Por Especialidade</h2>
          <div class="esp-list">
            <div *ngFor="let item of espItems(s.por_especialidade)" class="esp-row">
              <span class="esp-name">{{ item.esp }}</span>
              <div class="esp-bar-wrap">
                <div class="esp-bar" [style.width.%]="item.pct"></div>
              </div>
              <span class="esp-count">{{ item.count }}</span>
            </div>
          </div>
        </div>

        <!-- Dicas -->
        <div class="tip-box" *ngIf="s.por_rag < s.total_laudos * 0.5">
          <div class="tip-dot"></div>
          <div>
            <strong>Melhore a qualidade</strong>
            <p>Mais da metade dos laudos está sendo gerado sem referência no repositório. Adicione laudos de referência na aba <strong>Repositório</strong>.</p>
          </div>
        </div>
      </ng-container>
    </div>
  `,
  styles: [`
    .dash-page { padding: 32px 40px; height: 100%; overflow-y: auto; box-sizing: border-box; }
    .page-title { font-family: var(--font-heading); font-size: 24px; font-weight: 700; color: var(--colorNeutralForeground1); margin: 0 0 28px; letter-spacing: -0.02em; }
    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 32px; }
    .kpi-card { padding: 20px; border: 1px solid var(--colorNeutralStroke2); border-radius: 12px; background: var(--colorNeutralBackground2); display: flex; flex-direction: column; gap: 4px; }
    .kpi-accent { font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--colorBrandForeground1); }
    .kpi-val  { font-size: 32px; font-weight: 700; color: var(--colorNeutralForeground1); line-height: 1.1; }
    .kpi-val--good { color: #059669; }
    .kpi-val--warn { color: #d97706; }
    .kpi-lbl  { font-size: 12px; color: var(--colorNeutralForeground3); }
    .skeleton-kpi { height: 96px; border-radius: 12px; background: var(--colorNeutralBackground3); animation: shimmer 1.4s infinite; }
    @keyframes shimmer { 0%,100%{opacity:1} 50%{opacity:0.5} }
    .section { margin-bottom: 28px; }
    .section-title { font-size: 14px; font-weight: 600; color: var(--colorNeutralForeground2); margin: 0 0 16px; letter-spacing: 0.02em; text-transform: uppercase; }
    .esp-list { display: flex; flex-direction: column; gap: 12px; }
    .esp-row  { display: flex; align-items: center; gap: 12px; }
    .esp-name { min-width: 140px; font-size: 13px; color: var(--colorNeutralForeground1); }
    .esp-bar-wrap { flex: 1; background: var(--colorNeutralBackground4); border-radius: 4px; height: 6px; }
    .esp-bar  { height: 100%; background: var(--colorBrandForeground1); border-radius: 4px; transition: width 0.6s cubic-bezier(0.4,0,0.2,1); opacity: 0.7; }
    .esp-count { min-width: 30px; text-align: right; font-size: 13px; color: var(--colorNeutralForeground3); }
    .tip-box  { display: flex; gap: 14px; align-items: flex-start; padding: 16px; background: rgba(59,130,246,0.06); border: 1px solid rgba(59,130,246,0.2); border-radius: 10px; font-size: 14px; }
    .tip-dot  { width: 8px; height: 8px; border-radius: 50%; background: var(--colorBrandForeground1); flex-shrink: 0; margin-top: 5px; }
    .tip-box strong { display: block; margin-bottom: 4px; color: var(--colorBrandForeground1); font-size: 13px; }
    .tip-box p { margin: 0; color: var(--colorNeutralForeground2); font-size: 13px; line-height: 1.5; }
  `],
})
export class DashboardComponent implements OnInit {
  private laudoSvc = inject(LaudoService);
  stats   = signal<any>(null);
  loading = signal(true);

  ngOnInit() {
    this.laudoSvc.getDashboardStats().subscribe({
      next:  s  => { this.stats.set(s); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  espItems(obj: Record<string, number>) {
    const total = Object.values(obj).reduce((a, b) => a + b, 0);
    return Object.entries(obj)
      .sort(([,a],[,b]) => b - a)
      .map(([esp, count]) => ({ esp, count, pct: total ? (count / total) * 100 : 0 }));
  }
}


// ─────────────────────────────────────────────────────────────────────────────
// src/app/laudos/visualizar-laudo.component.ts
// ─────────────────────────────────────────────────────────────────────────────

import { Component, OnInit, signal, inject as inj } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { LaudoService, LaudoSalvo } from '../core/services/laudo.service';
import { VoiceService } from '../core/services/voice.service';
import { marked } from 'marked';

@Component({
  selector: 'app-visualizar-laudo',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="view-page" *ngIf="laudo() as l">
      <div class="view-header">
        <button class="btn-back" (click)="router.navigate(['/historico'])">← Voltar</button>
        <div class="view-info">
          <span class="esp-badge">{{ l.especialidade }}</span>
          <span class="data">{{ l.created_at | date:'dd/MM/yyyy HH:mm' }}</span>
          <span class="geracao-badge" [class]="l.tipo_geracao">
            {{ l.tipo_geracao === 'rag' ? 'Repositório' : 'Claude' }}
          </span>
        </div>
        <div class="view-actions">
          <button class="btn-action" (click)="voice.isSpeaking() ? voice.stopSpeaking() : lerLaudo()">
            {{ voice.isSpeaking() ? 'Parar' : 'Ouvir' }}
          </button>
          <button class="btn-action" (click)="editando.set(!editando())">
            {{ editando() ? 'Visualizar' : 'Editar' }}
          </button>
          <button class="btn-action primary" (click)="exportar('pdf')">PDF</button>
          <button class="btn-action" (click)="exportar('docx')">DOCX</button>
        </div>
      </div>

      <div class="view-body">
        <div *ngIf="!editando()" class="laudo-text markdown-body"
             [innerHTML]="renderMarkdown(l.laudo_editado || l.laudo)"></div>
        <textarea *ngIf="editando()" [(ngModel)]="textoEditado"
                  class="laudo-editor" rows="30" (blur)="salvarEdicao()"></textarea>
      </div>

      <div class="view-footer" *ngIf="!l.aprovado">
        <span class="footer-label">Laudo revisado?</span>
        <button class="btn-feedback ok" (click)="aprovar()">Aprovar</button>
        <button class="btn-feedback nok" (click)="showCorrecao.set(!showCorrecao())">Ajustes</button>
      </div>

      <div class="correcao-panel" *ngIf="showCorrecao()">
        <textarea class="correcao-input" [(ngModel)]="correcaoText"
                  placeholder="Descreva os ajustes necessários..." rows="3"></textarea>
        <div class="correcao-actions">
          <button class="btn-correcao-cancel" (click)="showCorrecao.set(false); correcaoText = ''">Cancelar</button>
          <button class="btn-correcao-submit" (click)="confirmarRejeicao(l.id)">Enviar feedback</button>
        </div>
      </div>

      <div class="view-footer aprovado" *ngIf="l.aprovado === true">Laudo aprovado</div>
    </div>

    <div class="loading" *ngIf="loading()">Carregando laudo...</div>
  `,
  styles: [`
    .view-page { padding: 24px 32px; height: 100%; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; box-sizing: border-box; }
    .view-header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    .btn-back { background: none; border: 1px solid var(--colorNeutralStroke1); border-radius: 6px; padding: 7px 14px; cursor: pointer; font-size: 13px; color: var(--colorNeutralForeground2); transition: background-color 0.12s; }
    .btn-back:hover { background: var(--colorNeutralBackground3); }
    .view-info { display: flex; gap: 10px; align-items: center; flex: 1; flex-wrap: wrap; }
    .esp-badge { font-size: 13px; font-weight: 700; color: var(--colorBrandForeground1); }
    .data { font-size: 12px; color: var(--colorNeutralForeground3); }
    .geracao-badge { font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 10px; letter-spacing: 0.02em; text-transform: uppercase; }
    .geracao-badge.rag { background: rgba(16,185,129,0.12); color: #10b981; border: 1px solid rgba(16,185,129,0.2); }
    .geracao-badge.fallback { background: rgba(245,158,11,0.12); color: #f59e0b; border: 1px solid rgba(245,158,11,0.2); }
    .view-actions { display: flex; gap: 8px; }
    .btn-action { padding: 7px 14px; border: 1px solid var(--colorNeutralStroke1); border-radius: 6px; background: transparent; font-size: 13px; cursor: pointer; color: var(--colorNeutralForeground1); transition: background-color 0.12s; }
    .btn-action:hover { background: var(--colorNeutralBackground3); }
    .btn-action.primary { background: var(--colorBrandBackground); color: white; border-color: transparent; }
    .btn-action.primary:hover { background: var(--colorBrandBackgroundHover); }
    .view-body { background: var(--colorNeutralBackground2); border: 1px solid var(--colorNeutralStroke2); border-radius: 10px; padding: 28px; flex: 1; }
    .laudo-text { font-size: 14px; line-height: 1.8; color: var(--colorNeutralForeground1); }
    .markdown-body h1,h2,h3 { font-weight: 700; margin: 14px 0 6px; }
    .markdown-body p { margin: 6px 0; }
    .markdown-body strong { font-weight: 700; }
    .laudo-editor { width: 100%; min-height: 400px; padding: 16px; border: 1px solid var(--colorNeutralStroke1); border-radius: 8px; font-family: var(--font-mono); font-size: 13px; line-height: 1.7; background: var(--colorNeutralBackground1); color: var(--colorNeutralForeground1); resize: vertical; outline: none; box-sizing: border-box; }
    .laudo-editor:focus { border-color: var(--colorBrandStroke1); }
    .view-footer { display: flex; align-items: center; gap: 10px; padding: 14px 0; border-top: 1px solid var(--colorNeutralStroke2); font-size: 14px; color: var(--colorNeutralForeground2); }
    .footer-label { font-size: 13px; color: var(--colorNeutralForeground3); }
    .view-footer.aprovado { color: #10b981; font-weight: 600; font-size: 13px; }
    .btn-feedback { padding: 7px 16px; border: 1px solid transparent; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; transition: opacity 0.12s; }
    .btn-feedback.ok  { background: rgba(16,185,129,0.12); color: #10b981; border-color: rgba(16,185,129,0.25); }
    .btn-feedback.nok { background: rgba(245,158,11,0.12); color: #f59e0b; border-color: rgba(245,158,11,0.25); }
    .btn-feedback:hover { opacity: 0.8; }
    .correcao-panel { display: flex; flex-direction: column; gap: 10px; padding: 16px; background: var(--colorNeutralBackground2); border: 1px solid var(--colorNeutralStroke1); border-radius: 10px; }
    .correcao-input { width: 100%; padding: 10px 14px; border: 1px solid var(--colorNeutralStroke1); border-radius: 8px; font-size: 13px; font-family: inherit; background: var(--colorNeutralBackground1); color: var(--colorNeutralForeground1); resize: none; outline: none; line-height: 1.5; box-sizing: border-box; }
    .correcao-input:focus { border-color: var(--colorBrandStroke1); }
    .correcao-actions { display: flex; gap: 8px; justify-content: flex-end; }
    .btn-correcao-cancel { padding: 7px 14px; border: 1px solid var(--colorNeutralStroke1); border-radius: 6px; background: transparent; font-size: 13px; cursor: pointer; color: var(--colorNeutralForeground2); }
    .btn-correcao-submit { padding: 7px 16px; border: none; border-radius: 6px; background: var(--colorBrandBackground); color: white; font-size: 13px; font-weight: 600; cursor: pointer; }
    .btn-correcao-submit:hover { background: var(--colorBrandBackgroundHover); }
    .loading { padding: 40px; text-align: center; color: var(--colorNeutralForeground3); font-size: 14px; }
  `],
})
export class VisualizarLaudoComponent implements OnInit {
  private route    = inj(ActivatedRoute);
  private laudoSvc = inj(LaudoService);
  readonly router  = inj(Router);
  readonly voice   = inj(VoiceService);

  laudo        = signal<LaudoSalvo | null>(null);
  loading      = signal(true);
  editando     = signal(false);
  showCorrecao = signal(false);
  textoEditado = '';
  correcaoText = '';

  ngOnInit() {
    const id = this.route.snapshot.paramMap.get('id')!;
    this.laudoSvc.get(id).subscribe({
      next:  l  => { this.laudo.set(l); this.textoEditado = l.laudo_editado || l.laudo; this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  lerLaudo() {
    const l = this.laudo();
    if (l) this.voice.speak(l.laudo_editado || l.laudo, 0.85);
  }

  salvarEdicao() {
    const l = this.laudo();
    if (!l || this.textoEditado === (l.laudo_editado || l.laudo)) return;
    this.laudoSvc.atualizar(l.id, this.textoEditado).subscribe(() => {
      this.laudo.update(cur => cur ? { ...cur, laudo_editado: this.textoEditado } : cur);
    });
  }

  aprovar() {
    const l = this.laudo();
    if (!l) return;
    this.laudoSvc.feedback(l.id, true).subscribe(() =>
      this.laudo.update(c => c ? { ...c, aprovado: true } : c)
    );
  }

  confirmarRejeicao(id: string) {
    const correcoes = this.correcaoText.trim() || undefined;
    this.laudoSvc.feedback(id, false, correcoes).subscribe(() => {
      this.laudo.update(cur => cur ? { ...cur, aprovado: false } : cur);
      this.showCorrecao.set(false);
      this.correcaoText = '';
    });
  }

  exportar(fmt: 'pdf' | 'docx') {
    const l = this.laudo();
    if (l) window.open(this.laudoSvc.exportar(l.id, fmt), '_blank');
  }

  renderMarkdown(t: string) { return marked(t) as string; }
}
