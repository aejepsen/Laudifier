// src/app/core/services/laudo.service.ts
import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, Subject } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthService } from '../auth/auth.service';

export interface LaudoGeradoChunk {
  type:           'meta' | 'token' | 'done' | 'error';
  text?:          string;
  tipo_geracao?:  'rag' | 'fallback';
  laudos_ref?:    any[];
  campos_faltando?: string[];
  laudo?:         string;
  laudo_id?:      string;
  score?:         number;
  error?:         string;
}

export interface LaudoSalvo {
  id:            string;
  especialidade: string;
  tipo_laudo?:   string;
  solicitacao:   string;
  laudo:         string;
  laudo_editado?: string;
  tipo_geracao:  string;
  aprovado?:     boolean;
  created_at:    string;
}

export const ESPECIALIDADES = [
  'Radiologia', 'Tomografia', 'Ressonância Magnética',
  'Ultrassonografia', 'Ecocardiografia', 'Mamografia',
  'Patologia', 'Anatomia Patológica', 'Citologia',
  'Endoscopia', 'Colonoscopia',
  'Cardiologia', 'Neurologia', 'Ortopedia',
  'Dermatologia', 'Oftalmologia', 'Ginecologia',
  'Urologia', 'Pediatria', 'Geral',
];

@Injectable({ providedIn: 'root' })
export class LaudoService {
  private http   = inject(HttpClient);
  private auth   = inject(AuthService);

  /** Gera laudo via streaming SSE */
  gerarLaudo(
    solicitacao:   string,
    especialidade: string,
    dadosClinicos: Record<string, string> = {},
    laudoId?:      string,
  ): Observable<LaudoGeradoChunk> {
    const subject = new Subject<LaudoGeradoChunk>();
    this._fetchStream({ solicitacao, especialidade, dados_clinicos: dadosClinicos, laudo_id: laudoId }, subject);
    return subject.asObservable();
  }

  /** Refina laudo existente com achados adicionais (Etapa 3) */
  corrigirLaudo(laudoId: string, achados: string): Observable<LaudoGeradoChunk> {
    const subject = new Subject<LaudoGeradoChunk>();
    this._fetchCorrigirStream(laudoId, { achados }, subject);
    return subject.asObservable();
  }

  private async _fetchCorrigirStream(laudoId: string, body: any, subject: Subject<LaudoGeradoChunk>) {
    try {
      const token = await this.auth.getToken();
      const resp  = await fetch(`${environment.apiUrl}/laudos/${laudoId}/corrigir`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body:    JSON.stringify(body),
      });
      await this._processStream(resp, subject);
    } catch (err: any) {
      subject.next({ type: 'error', error: err.message });
      subject.complete();
    }
  }

  private async _fetchStream(body: any, subject: Subject<LaudoGeradoChunk>) {
    try {
      const token = await this.auth.getToken();
      const resp  = await fetch(`${environment.apiUrl}/laudos/gerar`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body:    JSON.stringify(body),
      });

      await this._processStream(resp, subject);
    } catch (err: any) {
      subject.next({ type: 'error', error: err.message });
      subject.complete();
    }
  }

  private async _processStream(resp: Response, subject: Subject<LaudoGeradoChunk>) {
    const reader  = resp.body!.getReader();
    const decoder = new TextDecoder();
    let   buffer  = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const chunk = JSON.parse(line.slice(6));
          subject.next(chunk);
          if (chunk.type === 'done' || chunk.type === 'error') {
            subject.complete(); return;
          }
        } catch { /* incomplete line */ }
      }
    }
    subject.complete();
  }

  listar(page = 0, especialidade?: string): Observable<LaudoSalvo[]> {
    const params: any = { page, size: 20 };
    if (especialidade) params['especialidade'] = especialidade;
    return this.http.get<LaudoSalvo[]>(`${environment.apiUrl}/laudos`, { params });
  }

  get(id: string): Observable<LaudoSalvo> {
    return this.http.get<LaudoSalvo>(`${environment.apiUrl}/laudos/${id}`);
  }

  atualizar(id: string, laudoEditado: string): Observable<void> {
    return this.http.put<void>(`${environment.apiUrl}/laudos/${id}`, laudoEditado);
  }

  feedback(id: string, aprovado: boolean, correcoes?: string): Observable<void> {
    return this.http.post<void>(`${environment.apiUrl}/laudos/${id}/feedback`,
      { laudo_id: id, aprovado, correcoes });
  }

  exportar(id: string, formato: 'pdf' | 'docx' | 'txt'): string {
    return `${environment.apiUrl}/laudos/${id}/exportar/${formato}`;
  }

  getDashboardStats(): Observable<any> {
    return this.http.get(`${environment.apiUrl}/dashboard/stats`);
  }
}
