// src/app/login/login.component.ts
import { Component, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../core/auth/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="login-page">

      <!-- Ambient glow — CSS only, no image -->
      <div class="glow glow-1"></div>
      <div class="glow glow-2"></div>

      <div class="login-card">

        <div class="brand">
          <div class="brand-mark">
            <svg width="36" height="36" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect width="36" height="36" rx="10" fill="rgba(99,102,241,0.12)"/>
              <path d="M11 9v14h14" stroke="#818cf8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
              <circle cx="25" cy="25" r="2.5" fill="#818cf8"/>
            </svg>
          </div>
          <h1 class="brand-name">Laudifier</h1>
          <p class="brand-sub">Laudos médicos com IA — precisos e personalizados</p>
        </div>

        <div class="banner banner--error" *ngIf="error()">{{ error() }}</div>
        <div class="banner banner--success" *ngIf="success()">{{ success() }}</div>

        <!-- Login -->
        <form (ngSubmit)="submit()" *ngIf="!showRegister()">
          <div class="field">
            <label>Email</label>
            <input type="email" [(ngModel)]="email" name="email"
              placeholder="medico@hospital.com" required autocomplete="email" />
          </div>
          <div class="field">
            <label>Senha</label>
            <input type="password" [(ngModel)]="password" name="password"
              placeholder="••••••••" required autocomplete="current-password" />
          </div>
          <button type="submit" class="btn-primary" [disabled]="auth.loading()">
            <span *ngIf="!auth.loading()">Entrar</span>
            <span *ngIf="auth.loading()" class="spinner"></span>
          </button>
          <p class="toggle">Não tem conta?
            <button type="button" (click)="showRegister.set(true); error.set(''); success.set('')">Cadastrar</button>
          </p>
        </form>

        <!-- Registro -->
        <form (ngSubmit)="register()" *ngIf="showRegister()">
          <div class="field">
            <label>Nome completo</label>
            <input type="text" [(ngModel)]="nome" name="nome"
              placeholder="Dr. João Silva" required autocomplete="name" />
          </div>
          <div class="field">
            <label>CRM</label>
            <input type="text" [(ngModel)]="crm" name="crm" placeholder="12345/SP" />
          </div>
          <div class="field">
            <label>Email</label>
            <input type="email" [(ngModel)]="email" name="email"
              placeholder="medico@hospital.com" required autocomplete="email" />
          </div>
          <div class="field">
            <label>Senha</label>
            <input type="password" [(ngModel)]="password" name="password"
              placeholder="Mínimo 8 caracteres" required minlength="8" autocomplete="new-password" />
          </div>
          <button type="submit" class="btn-primary" [disabled]="auth.loading()">
            <span *ngIf="!auth.loading()">Criar conta</span>
            <span *ngIf="auth.loading()" class="spinner"></span>
          </button>
          <p class="toggle">Já tem conta?
            <button type="button" (click)="showRegister.set(false); error.set(''); success.set('')">Entrar</button>
          </p>
        </form>

      </div>
    </div>
  `,
  styles: [`
    /* ── Page shell ────────────────────────────────────────────────────────── */
    .login-page {
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #080810;
      padding: 24px;
      position: relative;
      overflow: hidden;
    }

    /* ── Ambient glows ─────────────────────────────────────────────────────── */
    .glow {
      position: absolute;
      border-radius: 50%;
      filter: blur(80px);
      pointer-events: none;
    }
    .glow-1 {
      width: 480px; height: 480px;
      top: -120px; left: -100px;
      background: radial-gradient(circle, rgba(99,102,241,0.18) 0%, transparent 70%);
    }
    .glow-2 {
      width: 360px; height: 360px;
      bottom: -80px; right: -60px;
      background: radial-gradient(circle, rgba(14,165,233,0.10) 0%, transparent 70%);
    }

    /* ── Card ──────────────────────────────────────────────────────────────── */
    .login-card {
      position: relative;
      z-index: 1;
      width: 100%;
      max-width: 400px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 20px;
      padding: 40px 36px;
      backdrop-filter: blur(24px);
    }

    /* ── Brand ─────────────────────────────────────────────────────────────── */
    .brand { text-align: center; margin-bottom: 32px; }
    .brand-mark { display: inline-flex; margin-bottom: 14px; }
    .brand-name {
      font-family: 'Syne', system-ui, sans-serif;
      font-size: 28px;
      font-weight: 700;
      letter-spacing: -0.03em;
      color: #f1f5f9;
      margin: 0 0 6px;
    }
    .brand-sub {
      font-size: 13px;
      color: rgba(255,255,255,0.38);
      margin: 0;
      line-height: 1.5;
    }

    /* ── Banners ───────────────────────────────────────────────────────────── */
    .banner {
      border-radius: 10px;
      padding: 10px 14px;
      font-size: 13px;
      margin-bottom: 20px;
      line-height: 1.5;
    }
    .banner--error {
      background: rgba(239,68,68,0.10);
      border: 1px solid rgba(239,68,68,0.25);
      color: #fca5a5;
    }
    .banner--success {
      background: rgba(34,197,94,0.10);
      border: 1px solid rgba(34,197,94,0.25);
      color: #86efac;
    }

    /* ── Fields ────────────────────────────────────────────────────────────── */
    .field { margin-bottom: 16px; }
    .field label {
      display: block;
      font-size: 12px;
      font-weight: 500;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: rgba(255,255,255,0.45);
      margin-bottom: 7px;
    }
    .field input {
      width: 100%;
      padding: 10px 14px;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.10);
      border-radius: 10px;
      font-size: 14px;
      font-family: 'DM Sans', system-ui, sans-serif;
      color: #f1f5f9;
      outline: none;
      box-sizing: border-box;
      transition: border-color 0.15s, box-shadow 0.15s;
    }
    .field input::placeholder { color: rgba(255,255,255,0.22); }
    .field input:focus {
      border-color: rgba(129,140,248,0.60);
      box-shadow: 0 0 0 3px rgba(99,102,241,0.15);
    }

    /* ── Primary button ────────────────────────────────────────────────────── */
    .btn-primary {
      width: 100%;
      padding: 11px;
      background: #6366f1;
      color: #fff;
      border: none;
      border-radius: 10px;
      font-size: 14px;
      font-family: 'DM Sans', system-ui, sans-serif;
      font-weight: 600;
      cursor: pointer;
      margin-top: 4px;
      margin-bottom: 18px;
      transition: background 0.15s, transform 0.1s;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 42px;
    }
    .btn-primary:hover:not(:disabled) { background: #818cf8; }
    .btn-primary:active:not(:disabled) { transform: scale(0.99); }
    .btn-primary:disabled { opacity: 0.45; cursor: not-allowed; }

    /* ── Spinner ───────────────────────────────────────────────────────────── */
    .spinner {
      width: 16px; height: 16px;
      border: 2px solid rgba(255,255,255,0.3);
      border-top-color: #fff;
      border-radius: 50%;
      animation: spin 0.65s linear infinite;
      display: inline-block;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* ── Toggle ────────────────────────────────────────────────────────────── */
    .toggle {
      text-align: center;
      font-size: 13px;
      color: rgba(255,255,255,0.35);
      margin: 0;
    }
    .toggle button {
      background: none;
      border: none;
      color: #818cf8;
      cursor: pointer;
      font-weight: 600;
      font-size: 13px;
      padding: 0;
      margin-left: 4px;
      transition: color 0.15s;
    }
    .toggle button:hover { color: #a5b4fc; }
  `],
})
export class LoginComponent {
  readonly auth = inject(AuthService);
  email = ''; password = ''; nome = ''; crm = '';
  error        = signal('');
  success      = signal('');
  showRegister = signal(false);

  async submit() {
    this.error.set('');
    try { await this.auth.signIn(this.email, this.password); }
    catch (e: any) { this.error.set(e.message || 'Email ou senha inválidos'); }
  }

  async register() {
    this.error.set('');
    this.success.set('');
    try {
      await this.auth.signUp(this.email, this.password, this.nome, this.crm);
      this.success.set('Conta criada! Verifique seu email para confirmar.');
      this.showRegister.set(false);
    } catch (e: any) { this.error.set(e.message || 'Erro ao criar conta'); }
  }
}
