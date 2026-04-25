// src/app/perfil/perfil.component.ts
import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../core/auth/auth.service';
import { ESPECIALIDADES } from '../core/services/laudo.service';

@Component({
  selector: 'app-perfil',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  template: `
    <div class="page">
      <header class="page-head">
        <div>
          <h1>Perfil</h1>
          <p class="sub">Atualize seus dados profissionais. Eles aparecem na assinatura dos laudos.</p>
        </div>
        <a routerLink="/gerar" class="btn-back">← Voltar</a>
      </header>

      <form class="card" (submit)="$event.preventDefault(); salvar()">
        <div class="field">
          <label>E-mail</label>
          <input type="email" [value]="email()" disabled />
          <span class="hint">Vinculado à conta — não editável.</span>
        </div>

        <div class="field">
          <label>Função</label>
          <input type="text" [value]="role()" disabled />
        </div>

        <div class="field">
          <label>Nome de exibição <span class="req">*</span></label>
          <input type="text" [(ngModel)]="displayName" name="displayName"
                 maxlength="100" placeholder="Dr(a). Nome Completo" required />
        </div>

        <div class="field">
          <label>CRM <span *ngIf="role() !== 'admin'" class="req">*</span></label>
          <input type="text" [(ngModel)]="crm" name="crm"
                 maxlength="40" placeholder="123456/SP" />
          <span class="hint" *ngIf="role() === 'admin'">
            Admin pode usar CRM fake (ex: <code>00000/TEST</code>) para testar geração como médico.
          </span>
        </div>

        <div class="field">
          <label>Especialidade principal</label>
          <select [(ngModel)]="especialidade" name="especialidade">
            <option value="">— Selecione —</option>
            <option *ngFor="let e of especialidades" [value]="e">{{ e }}</option>
          </select>
        </div>

        <div class="actions">
          <button type="submit" class="btn-primary"
                  [disabled]="!canSave() || salvando()">
            {{ salvando() ? 'Salvando…' : 'Salvar alterações' }}
          </button>
          <span class="status status-ok"  *ngIf="okMsg()">✓ {{ okMsg() }}</span>
          <span class="status status-err" *ngIf="errMsg()">✗ {{ errMsg() }}</span>
        </div>
      </form>
    </div>
  `,
  styles: [`
    .page { max-width: 720px; margin: 0 auto; padding: 32px 24px; }
    .page-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; gap: 16px; }
    .page-head h1 { margin: 0 0 4px 0; font-size: 28px; font-weight: 600; letter-spacing: -0.02em; }
    .sub { margin: 0; color: var(--colorNeutralForeground3); font-size: 14px; }
    .btn-back {
      color: var(--colorNeutralForeground2); text-decoration: none; font-size: 13px;
      padding: 8px 14px; border-radius: 6px;
    }
    .btn-back:hover { background: var(--colorNeutralBackground2); }

    .card {
      background: var(--colorNeutralBackground1);
      border: 1px solid var(--colorNeutralStroke2);
      border-radius: 10px;
      padding: 28px;
      display: flex; flex-direction: column; gap: 18px;
    }
    .field { display: flex; flex-direction: column; gap: 6px; }
    .field label {
      font-size: 12px; font-weight: 500; text-transform: uppercase;
      letter-spacing: 0.06em; color: var(--colorNeutralForeground2);
    }
    .req { color: #ef4444; }
    .field input, .field select {
      padding: 10px 12px; font-size: 14px;
      background: var(--colorNeutralBackground2);
      border: 1px solid var(--colorNeutralStroke1);
      border-radius: 6px; color: var(--colorNeutralForeground1);
      transition: border-color 120ms;
    }
    .field input:focus, .field select:focus {
      outline: none; border-color: #3b82f6;
      box-shadow: 0 0 0 3px rgba(59,130,246,0.15);
    }
    .field input:disabled { opacity: 0.55; cursor: not-allowed; }
    .hint { font-size: 12px; color: var(--colorNeutralForeground3); }
    .hint code {
      font-family: monospace; padding: 1px 5px; border-radius: 3px;
      background: var(--colorNeutralBackground2);
    }

    .actions { display: flex; align-items: center; gap: 14px; margin-top: 6px; }
    .btn-primary {
      padding: 10px 20px; font-size: 14px; font-weight: 500;
      background: #1a56db; color: #fff; border: none; border-radius: 6px;
      cursor: pointer; transition: background 120ms;
    }
    .btn-primary:hover:not(:disabled) { background: #1e40af; }
    .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
    .status { font-size: 13px; }
    .status-ok  { color: #10b981; }
    .status-err { color: #ef4444; }
  `],
})
export class PerfilComponent {
  private auth   = inject(AuthService);
  private router = inject(Router);

  especialidades = ESPECIALIDADES;

  displayName = '';
  crm         = '';
  especialidade = '';

  email = computed(() => this.auth.profile()?.email ?? '');
  role  = computed(() => this.auth.profile()?.role ?? 'medico');

  salvando = signal(false);
  okMsg    = signal('');
  errMsg   = signal('');

  constructor() {
    const p = this.auth.profile();
    if (!p) {
      this.router.navigate(['/login']);
      return;
    }
    this.displayName  = p.displayName ?? '';
    this.crm          = p.crm ?? '';
    this.especialidade = p.especialidade ?? '';
  }

  canSave(): boolean {
    return this.displayName.trim().length >= 2;
  }

  async salvar() {
    if (!this.canSave()) return;
    this.salvando.set(true);
    this.okMsg.set('');
    this.errMsg.set('');
    try {
      await this.auth.updateProfile({
        displayName:   this.displayName.trim(),
        crm:           this.crm.trim(),
        especialidade: this.especialidade,
      });
      this.okMsg.set('Perfil atualizado');
      setTimeout(() => this.okMsg.set(''), 3000);
    } catch (e: any) {
      this.errMsg.set(e?.message ?? 'Falha ao salvar');
    } finally {
      this.salvando.set(false);
    }
  }
}
