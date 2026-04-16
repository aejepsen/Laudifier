// src/app/core/auth/auth.service.ts
import { Injectable, signal } from '@angular/core';
import { Router } from '@angular/router';
import { inject } from '@angular/core';
import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { environment } from '../../../environments/environment';

export interface UserProfile {
  id: string; email: string; displayName: string;
  crm?: string; especialidade?: string; role: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private sb: SupabaseClient;
  private router = inject(Router);

  readonly profile    = signal<UserProfile | null>(null);
  readonly isLoggedIn = signal(false);
  readonly loading    = signal(false);

  constructor() {
    this.sb = createClient(environment.supabaseUrl, environment.supabaseKey, {
      auth: { lock: async (_name: string, _timeout: number, fn: () => Promise<unknown>) => fn() },
    });
    this.sb.auth.getSession().then(({ data }) => {
      if (data.session) {
        this.isLoggedIn.set(true);
        localStorage.setItem('sb-token', data.session.access_token);
        this._loadProfile(data.session.user.id, data.session.user.email ?? '');
      }
    });
    this.sb.auth.onAuthStateChange((_, session) => {
      this.isLoggedIn.set(!!session);
      if (session) {
        localStorage.setItem('sb-token', session.access_token);
        this._loadProfile(session.user.id, session.user.email ?? '');
      } else {
        localStorage.removeItem('sb-token');
        this.profile.set(null);
      }
    });
  }

  async signIn(email: string, password: string) {
    this.loading.set(true);
    try {
      const { error } = await this.sb.auth.signInWithPassword({ email, password });
      if (error) throw error;
      this.router.navigate(['/gerar']);
    } finally {
      this.loading.set(false);
    }
  }

  async signUp(email: string, password: string, nome: string, crm: string) {
    this.loading.set(true);
    const { data, error } = await this.sb.auth.signUp({ email, password });
    if (error) throw error;
    if (error) throw error;
    if (data.user) {
      await this.sb.from('user_profiles').insert({
        user_id: data.user.id, display_name: nome, crm, role: 'medico',
      });
    }
    this.loading.set(false);
  }

  async signOut() {
    await this.sb.auth.signOut();
    this.router.navigate(['/login']);
  }

  async getToken(): Promise<string> {
    const { data } = await this.sb.auth.getSession();
    return data.session?.access_token ?? '';
  }

  private async _loadProfile(userId: string, email: string) {
    const { data } = await this.sb.from('user_profiles')
      .select('*').eq('user_id', userId).single();
    this.profile.set({
      id: userId, email,
      displayName: data?.display_name ?? email.split('@')[0],
      crm:         data?.crm,
      especialidade: data?.especialidade,
      role:        data?.role ?? 'medico',
    });
  }
}
