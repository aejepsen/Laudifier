// src/app/core/services/voice.service.ts
/**
 * VoiceService para ditado médico.
 * STT: Web Speech API nativa do browser (PT-BR, grátis).
 * TTS: SpeechSynthesis API nativa.
 * Fallback: endpoint /laudos/transcrever (Whisper server-side).
 */
import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';

export type VoiceState = 'idle' | 'listening' | 'processing' | 'speaking' | 'error';

@Injectable({ providedIn: 'root' })
export class VoiceService {
  private http = inject(HttpClient);

  readonly state        = signal<VoiceState>('idle');
  readonly transcript   = signal('');
  readonly error        = signal('');
  readonly isSupported  = signal(false);
  readonly isSpeaking   = signal(false);

  private recognition: any = null;
  private synthesis = window.speechSynthesis;

  constructor() {
    const API = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (API) {
      this.isSupported.set(true);
      this.recognition = new API();
      this.recognition.continuous     = false;
      this.recognition.interimResults = true;
      this.recognition.lang           = 'pt-BR';
    }
  }

  // ── STT: escuta o médico ditar ──────────────────────────────────────────────

  startListening(): Promise<string> {
    if (!this.recognition) {
      // Fallback: grava áudio e envia para Whisper server-side
      return this._recordAndTranscribe();
    }

    return new Promise((resolve, reject) => {
      this.transcript.set('');
      this.error.set('');
      this.state.set('listening');

      this.recognition.onresult = (event: any) => {
        let final = '', interim = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const t = event.results[i][0].transcript;
          event.results[i].isFinal ? (final += t) : (interim += t);
        }
        this.transcript.set(final || interim);
        if (final) { this.state.set('processing'); resolve(final.trim()); }
      };

      this.recognition.onerror = (e: any) => {
        const msg = this._errorMsg(e.error);
        this.error.set(msg);
        this.state.set('error');
        reject(msg);
      };

      this.recognition.onend = () => {
        if (this.state() === 'listening') this.state.set('idle');
      };

      this.recognition.start();
    });
  }

  stopListening() {
    this.recognition?.stop();
    this.state.set('idle');
  }

  // ── TTS: lê o laudo gerado ─────────────────────────────────────────────────

  speak(text: string, rate = 0.9): Promise<void> {
    return new Promise((resolve) => {
      this.synthesis.cancel();
      const clean = this._stripMarkdown(text);
      if (!clean.trim()) { resolve(); return; }

      const utt  = new SpeechSynthesisUtterance(clean);
      utt.lang   = 'pt-BR';
      utt.rate   = rate;
      utt.pitch  = 1.0;

      // Prefere voz PT-BR local
      const voices = this.synthesis.getVoices();
      const ptVoice = voices.find(v => v.lang.startsWith('pt') && v.localService)
                   || voices.find(v => v.lang.startsWith('pt'));
      if (ptVoice) utt.voice = ptVoice;

      utt.onstart = () => { this.state.set('speaking'); this.isSpeaking.set(true); };
      utt.onend   = () => { this.state.set('idle'); this.isSpeaking.set(false); resolve(); };
      utt.onerror = () => { this.state.set('idle'); this.isSpeaking.set(false); resolve(); };

      this.synthesis.speak(utt);
    });
  }

  stopSpeaking() {
    this.synthesis.cancel();
    this.state.set('idle');
    this.isSpeaking.set(false);
  }

  // ── Fallback: Whisper server-side ─────────────────────────────────────────

  private async _recordAndTranscribe(): Promise<string> {
    this.state.set('listening');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks: Blob[] = [];

      recorder.ondataavailable = e => chunks.push(e.data);
      recorder.start();

      // Grava por 10 segundos ou até o médico parar
      await new Promise(r => setTimeout(r, 10000));
      recorder.stop();
      stream.getTracks().forEach(t => t.stop());

      await new Promise(r => (recorder.onstop = r));
      const blob = new Blob(chunks, { type: 'audio/webm' });

      this.state.set('processing');
      const form = new FormData();
      form.append('audio', blob, 'audio.webm');

      const result = await firstValueFrom(
        this.http.post<{ transcript: string }>(`${environment.apiUrl}/laudos/transcrever`, form)
      );
      this.state.set('idle');
      return result.transcript;
    } catch (e: any) {
      this.state.set('error');
      this.error.set('Erro ao gravar áudio: ' + e.message);
      throw e;
    }
  }

  private _stripMarkdown(t: string): string {
    return t.replace(/#{1,6}\s/g,'').replace(/\*\*(.+?)\*\*/g,'$1')
            .replace(/\*(.+?)\*/g,'$1').replace(/`[^`]*`/g,'')
            .replace(/\[(.+?)\]\(.+?\)/g,'$1').replace(/^\s*[-*+]\s/gm,'')
            .replace(/\n{2,}/g,'. ').trim();
  }

  private _errorMsg(code: string): string {
    const m: Record<string,string> = {
      'no-speech':    'Nenhuma fala detectada.',
      'not-allowed':  'Permissão de microfone negada. Habilite nas configurações.',
      'audio-capture':'Microfone não encontrado.',
      'network':      'Erro de rede.',
    };
    return m[code] ?? `Erro: ${code}`;
  }
}
