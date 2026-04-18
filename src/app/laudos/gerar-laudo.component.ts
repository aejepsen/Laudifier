// src/app/laudos/gerar-laudo.component.ts
/**
 * Componente principal do Laudifier.
 * Médico dita ou digita → IA gera o laudo → médico revisa e exporta.
 */
import {
  Component, signal, inject, computed, OnDestroy
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, takeUntil } from 'rxjs';
import { marked } from 'marked';
import { VoiceService } from '../core/services/voice.service';
import { LaudoService, ESPECIALIDADES, LaudoGeradoChunk } from '../core/services/laudo.service';

@Component({
  selector: 'app-gerar-laudo',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="laudo-page">

      <!-- ── Painel de Entrada ─────────────────────────────────────────────── -->
      <div class="input-panel" [class.collapsed]="laudoGerado()">

        <h2 class="panel-title">Novo Laudo</h2>

        <!-- Dados do Exame (opcional) -->
        <div class="field" *ngIf="showDados">
          <label>Dados do Exame <span class="optional">(opcional)</span></label>
          <div class="dados-grid">
            <input [(ngModel)]="dadosPaciente.nome"    placeholder="Nome do paciente" />
            <input [(ngModel)]="dadosPaciente.idade"   placeholder="Idade" />
            <input [(ngModel)]="dadosPaciente.sexo"    placeholder="Sexo" />
            <input [(ngModel)]="dadosPaciente.indicacao" placeholder="Indicação clínica" />
          </div>
        </div>
        <button class="btn-link" (click)="showDados = !showDados">
          {{ showDados ? '▲ Ocultar dados' : '▼ Adicionar dados do paciente' }}
        </button>

        <!-- Solicitação do Médico -->
        <div class="field">
          <label>Descreva o exame / achados</label>
          <div class="input-voice-wrap">
            <textarea
              [(ngModel)]="solicitacao"
              [placeholder]="voicePlaceholder()"
              rows="5"
              class="text-input"
              [class.listening]="voice.state() === 'listening'">
            </textarea>

            <!-- Botão de Voz -->
            <button
              class="btn-voice"
              [class.recording]="voice.state() === 'listening'"
              [class.processing]="voice.state() === 'processing'"
              [disabled]="isGenerating()"
              (click)="toggleVoice()"
              [title]="voiceBtnTitle()">
              <span class="voice-icon">{{ voiceIcon() }}</span>
              <span class="voice-label">{{ voiceBtnLabel() }}</span>
            </button>
          </div>

          <!-- Transcrição em tempo real -->
          <p class="live-transcript" *ngIf="voice.state() === 'listening' && voice.transcript()">
            <span class="dot"></span>{{ voice.transcript() }}
          </p>
          <p class="voice-error" *ngIf="voice.error()">⚠️ {{ voice.error() }}</p>
        </div>

        <!-- Botão Gerar -->
        <button
          class="btn-gerar"
          [disabled]="!canGenerate()"
          (click)="gerarLaudo()">
          <span *ngIf="!isGenerating()">Gerar Laudo</span>
          <span *ngIf="isGenerating()" class="generating">
            <span class="dots"><span></span><span></span><span></span></span>
            Gerando...
          </span>
        </button>

      </div>

      <!-- ── Painel do Laudo Gerado ─────────────────────────────────────────── -->
      <div class="result-panel" *ngIf="laudoGerado() || isGenerating()">

        <!-- Header com badges -->
        <div class="result-header">
          <h2 class="panel-title">Laudo Gerado</h2>
          <div class="badges">
            <span class="badge" [class]="tipoGeracao()" *ngIf="tipoGeracao()">
              {{ tipoGeracao() === 'rag' ? 'Repositório' : 'Claude' }}
            </span>
            <span class="badge refs" *ngIf="laudosRef().length > 0">
              {{ laudosRef().length }} referência(s)
            </span>
          </div>
          <!-- Ações -->
          <div class="result-actions" *ngIf="laudoGerado()">
            <button class="btn-action" (click)="lerLaudo()" [disabled]="voice.isSpeaking()">
              {{ voice.isSpeaking() ? '🔊 Lendo...' : '🔊 Ouvir' }}
            </button>
            <button class="btn-action" (click)="editando.set(!editando())">
              {{ editando() ? '👁 Visualizar' : '✏️ Editar' }}
            </button>
            <button class="btn-action primary" (click)="exportar('pdf')">⬇️ PDF</button>
            <button class="btn-action" (click)="exportar('docx')">⬇️ DOCX</button>
            <button class="btn-novo" (click)="novoLaudo()">+ Novo Laudo</button>
          </div>
        </div>

        <!-- Campos faltando -->
        <div class="campos-alert" *ngIf="camposFaltando().length > 0">
          <strong>📝 Preencha antes de finalizar:</strong>
          <span *ngFor="let c of camposFaltando()" class="campo-tag">[{{ c }}]</span>
        </div>

        <!-- Laudo em streaming / visualização -->
        <div class="laudo-content" *ngIf="!editando()">
          <div class="laudo-text markdown-body"
               [innerHTML]="renderMarkdown(laudoGerado())">
          </div>
          <div class="typing-cursor" *ngIf="isGenerating()">▌</div>
        </div>

        <!-- Laudo em edição -->
        <textarea
          *ngIf="editando()"
          [(ngModel)]="laudoEditado"
          class="laudo-editor"
          rows="30">
        </textarea>

        <!-- Complementar laudo com achados adicionais -->
        <div class="complementar-bar" *ngIf="laudoGerado() && !isGenerating() && currentLaudoId()">
          <div class="complementar-header">
            <span class="complementar-label">📝 Complementar com achados</span>
            <button class="btn-link" (click)="showComplementar = !showComplementar">
              {{ showComplementar ? '▲ Fechar' : '▼ Adicionar informações ao laudo' }}
            </button>
          </div>
          <div class="complementar-body" *ngIf="showComplementar">
            <div class="input-voice-wrap">
              <textarea
                [(ngModel)]="achados"
                placeholder="Descreva os achados adicionais em linguagem livre. Ex: &quot;Trauma de crânio com edema frontal, sem sangramento ativo&quot;"
                rows="3"
                class="text-input"
                [class.listening]="voice.state() === 'listening'">
              </textarea>
              <button
                class="btn-voice"
                [class.recording]="voice.state() === 'listening'"
                [disabled]="isRefining()"
                (click)="toggleVoiceAchados()"
                title="Ditar achados">
                <span class="voice-icon">{{ voice.state() === 'listening' ? '⏹' : '🎙️' }}</span>
              </button>
            </div>
            <button
              class="btn-gerar"
              style="margin-top: 0.5rem"
              [disabled]="!achados.trim() || isRefining()"
              (click)="refinarLaudo()">
              <span *ngIf="!isRefining()">Refinar Laudo</span>
              <span *ngIf="isRefining()" class="generating">
                <span class="dots"><span></span><span></span><span></span></span>
                Refinando...
              </span>
            </button>
          </div>
        </div>

        <!-- Feedback do médico -->
        <div class="feedback-bar" *ngIf="laudoGerado() && !isGenerating() && !isRefining()">
          <span class="feedback-label">Este laudo está correto?</span>
          <button class="btn-feedback ok"    (click)="feedback(true)">👍 Aprovar</button>
          <button class="btn-feedback nok"   (click)="feedback(false)">✏️ Precisa de ajustes</button>
        </div>

      </div>

    </div>
  `,
  styleUrls: ['./gerar-laudo.component.scss'],
})
export class GerarLaudoComponent implements OnDestroy {
  readonly voice = inject(VoiceService);
  private  laudoSvc = inject(LaudoService);
  private  destroy$ = new Subject<void>();

  especialidade    = 'Geral';
  solicitacao      = '';
  showDados        = false;
  showComplementar = false;
  achados          = '';
  dadosPaciente  = { nome: '', idade: '', sexo: '', indicacao: '' };
  laudoEditado   = '';

  laudoGerado    = signal('');
  tipoGeracao    = signal<'rag' | 'fallback' | ''>('');
  laudosRef      = signal<any[]>([]);
  camposFaltando = signal<string[]>([]);
  isGenerating   = signal(false);
  isRefining     = signal(false);
  editando       = signal(false);
  currentLaudoId = signal('');

  canGenerate() {
    return !!this.solicitacao.trim() && !this.isGenerating();
  }

  voicePlaceholder = computed(() => {
    if (this.voice.state() === 'listening')  return '🎙️ Ouvindo... fale os achados do exame';
    if (this.voice.state() === 'processing') return '⏳ Processando...';
    return 'Digite ou dite os achados do exame. Ex: "RX de tórax PA, campos pulmonares sem condensações, seios costofrênicos livres..."';
  });

  voiceIcon = computed(() => {
    const icons: Record<string, string> = {
      idle: '🎙️', listening: '⏹', processing: '⏳', speaking: '🔊', error: '⚠️'
    };
    return icons[this.voice.state()] ?? '🎙️';
  });

  voiceBtnLabel = computed(() => {
    const labels: Record<string, string> = {
      idle: 'Ditar', listening: 'Parar', processing: 'Processando...', error: 'Tentar novamente'
    };
    return labels[this.voice.state()] ?? 'Ditar';
  });

  voiceBtnTitle = computed(() =>
    this.voice.isSupported()
      ? 'Ditar usando o microfone (PT-BR)'
      : 'Reconhecimento de voz não disponível neste browser'
  );

  async toggleVoice() {
    if (this.voice.state() === 'listening') {
      this.voice.stopListening();
      return;
    }
    try {
      const texto = await this.voice.startListening();
      this.solicitacao = texto;
    } catch (e) { /* erro já em voice.error() */ }
  }

  async toggleVoiceAchados() {
    if (this.voice.state() === 'listening') {
      this.voice.stopListening();
      return;
    }
    try {
      const texto = await this.voice.startListening();
      this.achados = texto;
    } catch (e) { /* erro já em voice.error() */ }
  }

  refinarLaudo() {
    if (!this.achados.trim() || !this.currentLaudoId() || this.isRefining()) return;
    this.isRefining.set(true);
    this.editando.set(false);

    this.laudoSvc
      .corrigirLaudo(this.currentLaudoId(), this.achados)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (chunk: LaudoGeradoChunk) => {
          if (chunk.type === 'token') {
            this.laudoGerado.update(t => t + (chunk.text ?? ''));
          }
          if (chunk.type === 'done') {
            this.camposFaltando.set(chunk.campos_faltando ?? []);
            this.laudoEditado = chunk.laudo ?? this.laudoGerado();
            this.achados = '';
            this.showComplementar = false;
            this.isRefining.set(false);
          }
          if (chunk.type === 'error') {
            this.isRefining.set(false);
          }
        },
        complete: () => this.isRefining.set(false),
      });

    // Limpa o laudo atual para mostrar o refinado em streaming
    this.laudoGerado.set('');
  }

  gerarLaudo() {
    if (!this.canGenerate()) return;
    this.laudoGerado.set('');
    this.tipoGeracao.set('');
    this.laudosRef.set([]);
    this.camposFaltando.set([]);
    this.isGenerating.set(true);
    this.editando.set(false);

    const dados: Record<string, string> = {};
    if (this.dadosPaciente.nome)      dados['paciente']   = this.dadosPaciente.nome;
    if (this.dadosPaciente.idade)     dados['idade']      = this.dadosPaciente.idade;
    if (this.dadosPaciente.sexo)      dados['sexo']       = this.dadosPaciente.sexo;
    if (this.dadosPaciente.indicacao) dados['indicacao']  = this.dadosPaciente.indicacao;

    this.laudoSvc
      .gerarLaudo(this.solicitacao, this.especialidade, dados)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (chunk: LaudoGeradoChunk) => {
          if (chunk.type === 'token') {
            this.laudoGerado.update(t => t + (chunk.text ?? ''));
          }
          if (chunk.type === 'meta') {
            this.tipoGeracao.set(chunk.tipo_geracao ?? '');
            this.laudosRef.set(chunk.laudos_ref ?? []);
          }
          if (chunk.type === 'done') {
            this.camposFaltando.set(chunk.campos_faltando ?? []);
            this.laudoEditado = chunk.laudo ?? this.laudoGerado();
            this.currentLaudoId.set(chunk.laudo_id ?? '');
            this.isGenerating.set(false);
          }
          if (chunk.type === 'error') {
            this.isGenerating.set(false);
          }
        },
        complete: () => this.isGenerating.set(false),
      });
  }

  renderMarkdown(text: string): string {
    return marked(text) as string;
  }

  lerLaudo() {
    if (this.voice.isSpeaking()) {
      this.voice.stopSpeaking();
    } else {
      this.voice.speak(this.laudoGerado(), 0.85);
    }
  }

  feedback(aprovado: boolean) {
    if (!this.currentLaudoId()) return;
    const correcoes = !aprovado ? prompt('Descreva os ajustes necessários (opcional):') ?? undefined : undefined;
    this.laudoSvc.feedback(this.currentLaudoId(), aprovado, correcoes)
      .pipe(takeUntil(this.destroy$)).subscribe();
  }

  exportar(formato: 'pdf' | 'docx' | 'txt') {
    if (!this.currentLaudoId()) return;
    const url = this.laudoSvc.exportar(this.currentLaudoId(), formato);
    window.open(url, '_blank');
  }

  novoLaudo() {
    this.laudoGerado.set('');
    this.solicitacao = '';
    this.especialidade = 'Geral';
    this.tipoGeracao.set('');
    this.camposFaltando.set([]);
    this.editando.set(false);
    this.achados = '';
    this.showComplementar = false;
    this.currentLaudoId.set('');
  }

  ngOnDestroy() {
    this.destroy$.next();
    this.destroy$.complete();
    this.voice.stopSpeaking();
  }
}
