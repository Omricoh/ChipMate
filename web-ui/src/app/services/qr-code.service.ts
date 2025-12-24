import { Injectable } from '@angular/core';
import * as QRCode from 'qrcode';

@Injectable({
  providedIn: 'root'
})
export class QrCodeService {

  constructor() {}

  async generateQRCode(text: string, options?: any): Promise<string> {
    try {
      // @ts-ignore - QRCode types incorrectly return void, but runtime returns Promise<string>
      const qrCodeDataURL: string = await QRCode.toDataURL(text, {
        errorCorrectionLevel: 'M',
        type: 'image/png',
        quality: 0.92,
        margin: 2,
        color: {
          dark: '#2c3e50',
          light: '#FFFFFF'
        },
        width: 256,
        ...options
      });
      return qrCodeDataURL;
    } catch (error) {
      console.error('Error generating QR code:', error);
      throw error;
    }
  }

  async generateGameJoinQR(gameCode: string, baseUrl: string = window.location.origin): Promise<string> {
    const joinUrl = `${baseUrl}/join/${gameCode}`;
    return this.generateQRCode(joinUrl, {
      width: 300,
      margin: 3
    });
  }
}