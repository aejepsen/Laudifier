// src/app/laudos/gerar-laudo.component.ts
/**
 * Componente principal do Laudifier.
 * Médico dita ou digita → IA gera o laudo → médico revisa e exporta.
 */
import {
  Component, signal, inject, computed, OnDestroy, ViewChild, ElementRef
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
      <div class="input-panel" [class.collapsed]="isGenerating() && !laudoGerado()">

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
              [class.listening]="voice.state() === 'listening' && editandoLinha() === 0 && adicionandoApos() === 0">
            </textarea>

            <!-- Botão de Voz -->
            <button
              class="btn-voice"
              [class.recording]="voice.state() === 'listening' && editandoLinha() === 0 && adicionandoApos() === 0"
              [class.processing]="voice.state() === 'processing'"
              [disabled]="isGenerating()"
              (click)="toggleVoice()"
              [title]="voiceBtnTitle()">
              <span class="voice-icon">{{ voiceIcon() }}</span>
              <span class="voice-label">{{ voiceBtnLabel() }}</span>
            </button>
          </div>

          <!-- Transcrição em tempo real -->
          <p class="live-transcript" *ngIf="voice.state() === 'listening' && voice.transcript() && editandoLinha() === 0">
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

        <!-- ── Refinar / Editar linha (aparece após gerar laudo) ──────────── -->
        <div class="refinar-section" *ngIf="currentLaudoId() && !isGenerating()">
          <div class="refinar-divider"></div>

          <!-- Label dinâmico: linha selecionada ou geral -->
          <div class="refinar-label">
            <span *ngIf="editandoLinha() === 0">📝 Adicionar informações ao laudo</span>
            <span *ngIf="editandoLinha() > 0" class="refinar-linha-badge">
              ✏️ Editando linha {{ editandoLinha() }}
              <button class="btn-link-small" (click)="cancelarEdicaoLinha()">× cancelar seleção</button>
            </span>
          </div>

          <div class="input-voice-wrap">
            <textarea
              #refinarTextarea
              [(ngModel)]="achados"
              [placeholder]="refinarPlaceholder()"
              rows="4"
              class="text-input"
              [class.listening]="voice.state() === 'listening' && (editandoLinha() > 0 || adicionandoApos() > 0)"
              [class.linha-selecionada]="editandoLinha() > 0">
            </textarea>
            <button
              class="btn-voice"
              [class.recording]="voice.state() === 'listening' && editandoLinha() >= 0"
              [disabled]="isRefining()"
              (click)="toggleVoiceAchados()"
              title="Ditar">
              <span class="voice-icon">{{ voice.state() === 'listening' ? '⏹' : '🎙️' }}</span>
            </button>
          </div>

          <!-- Live transcript para ditar no refinar -->
          <p class="live-transcript" *ngIf="voice.state() === 'listening' && voice.transcript() && editandoLinha() > 0">
            <span class="dot"></span>{{ voice.transcript() }}
          </p>

          <button
            class="btn-refinar"
            [disabled]="!achados.trim() || isRefining()"
            (click)="refinarLaudo()">
            <span *ngIf="!isRefining()">
              {{ editandoLinha() > 0 ? 'Aplicar na linha ' + editandoLinha() : 'Refinar Laudo' }}
            </span>
            <span *ngIf="isRefining()" class="generating">
              <span class="dots"><span></span><span></span><span></span></span>
              Refinando...
            </span>
          </button>
        </div>

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

          <!-- Toggle modo linhas -->
          <div class="modo-linhas-bar" *ngIf="laudoGerado() && !isGenerating() && !isRefining()">
            <button class="btn-link" (click)="modoLinhas.set(!modoLinhas())">
              {{ modoLinhas() ? '👁 Visualização normal' : '🔢 Editar por linha' }}
            </button>
          </div>

          <!-- Modo normal: markdown renderizado (tabelas, bold, headers) -->
          <div *ngIf="!modoLinhas()" class="laudo-text markdown-body"
               [innerHTML]="renderMarkdown(laudoGerado())">
          </div>

          <!-- Modo linhas: checkbox para selecionar (edita no painel esquerdo), + para inserir, × para deletar -->
          <div *ngIf="modoLinhas()" class="laudo-numbered">
            <ng-container *ngFor="let linha of laudoLinhas()">
              <div *ngIf="linha.isEmpty" class="linha-spacer"></div>
              <ng-container *ngIf="!linha.isEmpty">

                <div class="laudo-linha" [class.linha-ativa]="editandoLinha() === linha.num">
                  <input type="checkbox" class="linha-check"
                    [checked]="editandoLinha() === linha.num"
                    (change)="toggleEditarLinha(linha.num, linha.text)"
                    title="Selecionar para editar" />
                  <span class="linha-num">{{ linha.num }}</span>
                  <span class="linha-text" [innerHTML]="renderLine(linha.text)"></span>
                  <span class="linha-acoes">
                    <button class="btn-linha-add" (click)="iniciarAdicao(linha.num)" title="Inserir linha após">+</button>
                    <button class="btn-linha-del" (click)="deletarLinha(linha.num)" title="Remover linha">×</button>
                  </span>
                </div>

                <!-- Input inline apenas para nova linha -->
                <div *ngIf="adicionandoApos() === linha.num" class="linha-nova">
                  <span class="linha-num">{{ linha.num + 1 }}</span>
                  <input
                    class="linha-nova-input"
                    [(ngModel)]="novaLinhaTexto"
                    [placeholder]="voice.state() === 'listening' ? '🎙️ Ouvindo...' : 'Digite ou dite o texto da nova linha...'"
                    (keydown.enter)="confirmarAdicao()"
                    (keydown.escape)="cancelarAdicao()" />
                  <button class="btn-linha-voice" [class.recording]="voice.state() === 'listening'"
                    (click)="toggleVoiceNovaLinha()" title="Ditar">
                    {{ voice.state() === 'listening' ? '⏹' : '🎙️' }}
                  </button>
                  <button class="btn-linha-ok"     (click)="confirmarAdicao()">✓</button>
                  <button class="btn-linha-cancel" (click)="cancelarAdicao()">×</button>
                </div>

              </ng-container>
            </ng-container>
          </div>

          <div class="typing-cursor" *ngIf="isGenerating() || isRefining()">▌</div>
        </div>

        <!-- Laudo em edição -->
        <textarea
          *ngIf="editando()"
          [(ngModel)]="laudoEditado"
          class="laudo-editor"
          rows="30">
        </textarea>

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

  @ViewChild('refinarTextarea') refinarTextareaRef?: ElementRef<HTMLTextAreaElement>;

  especialidade = 'Geral';
  solicitacao   = '';
  showDados     = false;
  achados       = '';
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
  adicionandoApos   = signal(0);
  modoLinhas        = signal(false);
  editandoLinha     = signal(0);
  novaLinhaTexto = '';

  canGenerate() {
    return !!this.solicitacao.trim() && !this.isGenerating();
  }

  laudoLinhas = computed(() => {
    const lines = this.laudoGerado().split('\n');
    let num = 0;
    return lines.map(line => ({
      isEmpty: !line.trim(),
      num:     line.trim() ? ++num : 0,
      text:    line,
    }));
  });

  refinarPlaceholder = computed(() => {
    const num = this.editandoLinha();
    if (this.voice.state() === 'listening') return '🎙️ Ouvindo...';
    if (num > 0) return `Dite ou digite a correção para a linha ${num}. Ex: "fibrose periportal leve"`;
    return 'Dite o número da linha e o novo texto. Ex: "16 a lesão mede 2 x 2 cm" ou acrescente achados gerais.';
  });

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
    // Se uma linha estiver selecionada, prepend o número para o backend resolver
    const payload = this.editandoLinha() > 0
      ? `${this.editandoLinha()} ${this.achados.trim()}`
      : this.achados.trim();
    this.isRefining.set(true);
    this.editando.set(false);
    this.cancelarEdicaoLinha();

    let primeiroToken = true;

    this.laudoSvc
      .corrigirLaudo(this.currentLaudoId(), payload)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (chunk: LaudoGeradoChunk) => {
          if (chunk.type === 'token') {
            // Só apaga o laudo anterior quando o primeiro token chega
            if (primeiroToken) {
              this.laudoGerado.set('');
              primeiroToken = false;
            }
            this.laudoGerado.update(t => t + (chunk.text ?? ''));
          }
          if (chunk.type === 'done') {
            this.camposFaltando.set(chunk.campos_faltando ?? []);
            this.laudoEditado = chunk.laudo ?? this.laudoGerado();
            this.achados = '';
            this.isRefining.set(false);
          }
          if (chunk.type === 'error') {
            this.isRefining.set(false);
          }
        },
        complete: () => this.isRefining.set(false),
      });
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

  renderLine(text: string): string {
    return text
      .replace(/^#{1,6}\s+(.+)/, '<strong>$1</strong>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');
  }

  deletarLinha(num: number) {
    const linhas = this.laudoGerado().split('\n');
    let contador = 0;
    const resultado = linhas.filter(linha => {
      if (linha.trim()) { contador++; return contador !== num; }
      return true;
    });
    const novo = resultado.join('\n');
    this.laudoGerado.set(novo);
    this.laudoEditado = novo;
  }

  iniciarAdicao(num: number) {
    this.adicionandoApos.set(num);
    this.novaLinhaTexto = '';
  }

  confirmarAdicao() {
    if (!this.novaLinhaTexto.trim()) { this.cancelarAdicao(); return; }
    const num = this.adicionandoApos();
    const linhas = this.laudoGerado().split('\n');
    let contador = 0;
    let insertIdx = linhas.length;
    for (let i = 0; i < linhas.length; i++) {
      if (linhas[i].trim()) {
        contador++;
        if (contador === num) { insertIdx = i + 1; break; }
      }
    }
    linhas.splice(insertIdx, 0, this.novaLinhaTexto.trim());
    const novo = linhas.join('\n');
    this.laudoGerado.set(novo);
    this.laudoEditado = novo;
    this.cancelarAdicao();
  }

  cancelarAdicao() {
    this.adicionandoApos.set(0);
    this.novaLinhaTexto = '';
    this.voice.stopListening();
  }

  toggleEditarLinha(num: number, _textoAtual: string) {
    if (this.editandoLinha() === num) {
      this.cancelarEdicaoLinha();
    } else {
      this.editandoLinha.set(num);
      this.achados = '';
      this.voice.stopListening();
      // Redireciona foco para o textarea no painel esquerdo
      setTimeout(() => {
        this.refinarTextareaRef?.nativeElement?.focus();
        this.refinarTextareaRef?.nativeElement?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }, 50);
    }
  }

  cancelarEdicaoLinha() {
    this.editandoLinha.set(0);
    this.voice.stopListening();
  }

  async toggleVoiceNovaLinha() {
    if (this.voice.state() === 'listening') {
      this.voice.stopListening();
      return;
    }
    try {
      const texto = await this.voice.startListening();
      this.novaLinhaTexto = texto;
    } catch (e) { /* erro já em voice.error() */ }
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
    this.currentLaudoId.set('');
    this.modoLinhas.set(false);
    this.editandoLinha.set(0);
  }

  ngOnDestroy() {
    this.destroy$.next();
    this.destroy$.complete();
    this.voice.stopSpeaking();
  }
}
