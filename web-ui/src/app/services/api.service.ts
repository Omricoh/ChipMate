import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable, BehaviorSubject } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  Game,
  Player,
  Transaction,
  GameStatus,
  PlayerSummary,
  CashoutRequest,
  BuyinRequest,
  GameLink,
  SettlementStatus,
  SettlementSummary,
  AllSettlementSummaries,
  UnpaidCredit
} from '../models/game.model';
import { User, AuthRequest, AuthResponse } from '../models/user.model';

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private baseUrl = environment.apiUrl;
  private currentUserSubject = new BehaviorSubject<User | null>(null);
  public currentUser$ = this.currentUserSubject.asObservable();

  constructor(private http: HttpClient) {
    // Try to restore user from localStorage
    const savedUser = localStorage.getItem('chipmate_user');
    if (savedUser) {
      this.currentUserSubject.next(JSON.parse(savedUser));
    }
  }

  private getHeaders(): HttpHeaders {
    return new HttpHeaders({
      'Content-Type': 'application/json'
    });
  }

  // Authentication
  login(authRequest: AuthRequest): Observable<AuthResponse> {
    return this.http.post<AuthResponse>(`${this.baseUrl}/auth/login`, authRequest, {
      headers: this.getHeaders()
    });
  }

  setCurrentUser(user: User): void {
    this.currentUserSubject.next(user);
    localStorage.setItem('chipmate_user', JSON.stringify(user));
  }

  logout(): void {
    this.currentUserSubject.next(null);
    localStorage.removeItem('chipmate_user');
  }

  getCurrentUser(): User | null {
    return this.currentUserSubject.value;
  }

  // Game Management
  createGame(hostName: string): Observable<{ game_id: string; game_code: string; host_user_id: number }> {
    const currentUser = this.getCurrentUser();
    const requestBody: any = {
      host_name: hostName
    };

    // Include user_id if user is logged in
    if (currentUser && currentUser.id) {
      requestBody.user_id = currentUser.id;
    }

    return this.http.post<{ game_id: string; game_code: string; host_user_id: number }>(`${this.baseUrl}/games`, requestBody, { headers: this.getHeaders() });
  }

  joinGame(gameCode: string, userName: string): Observable<{ game_id: string; message: string }> {
    return this.http.post<{ game_id: string; message: string }>(`${this.baseUrl}/games/join`, {
      code: gameCode,
      user_name: userName
    }, { headers: this.getHeaders() });
  }

  getGame(gameId: string): Observable<Game> {
    return this.http.get<Game>(`${this.baseUrl}/games/${gameId}`, {
      headers: this.getHeaders()
    });
  }

  getGameStatus(gameId: string): Observable<GameStatus> {
    return this.http.get<GameStatus>(`${this.baseUrl}/games/${gameId}/status`, {
      headers: this.getHeaders()
    });
  }

  getGamePlayers(gameId: string): Observable<Player[]> {
    return this.http.get<Player[]>(`${this.baseUrl}/games/${gameId}/players`, {
      headers: this.getHeaders()
    });
  }

  endGame(gameId: string): Observable<{ message: string }> {
    return this.http.post<{ message: string }>(`${this.baseUrl}/games/${gameId}/end`, {}, {
      headers: this.getHeaders()
    });
  }

  // Generate game link with QR code
  generateGameLink(gameCode: string): Observable<GameLink> {
    return this.http.get<GameLink>(`${this.baseUrl}/games/${gameCode}/link`, {
      headers: this.getHeaders()
    });
  }

  // Transactions
  createBuyin(buyinRequest: BuyinRequest): Observable<{ transaction_id: string; message: string }> {
    return this.http.post<{ transaction_id: string; message: string }>(`${this.baseUrl}/transactions/buyin`, buyinRequest, {
      headers: this.getHeaders()
    });
  }

  createCashout(cashoutRequest: CashoutRequest): Observable<{ transaction_id: string; message: string }> {
    return this.http.post<{ transaction_id: string; message: string }>(`${this.baseUrl}/transactions/cashout`, cashoutRequest, {
      headers: this.getHeaders()
    });
  }

  getPendingTransactions(gameId: string): Observable<Transaction[]> {
    return this.http.get<Transaction[]>(`${this.baseUrl}/games/${gameId}/transactions/pending`, {
      headers: this.getHeaders()
    });
  }

  approveTransaction(transactionId: string): Observable<{ message: string }> {
    return this.http.post<{ message: string }>(`${this.baseUrl}/transactions/${transactionId}/approve`, {}, {
      headers: this.getHeaders()
    });
  }

  rejectTransaction(transactionId: string): Observable<{ message: string }> {
    return this.http.post<{ message: string }>(`${this.baseUrl}/transactions/${transactionId}/reject`, {}, {
      headers: this.getHeaders()
    });
  }

  // Player Status
  getPlayerSummary(gameId: string, userId: number): Observable<PlayerSummary> {
    return this.http.get<PlayerSummary>(`${this.baseUrl}/games/${gameId}/players/${userId}/summary`, {
      headers: this.getHeaders()
    });
  }

  // Settlement Management
  startSettlement(gameId: string): Observable<SettlementStatus> {
    return this.http.post<SettlementStatus>(`${this.baseUrl}/games/${gameId}/settlement/start`, {}, {
      headers: this.getHeaders()
    });
  }

  getSettlementStatus(gameId: string): Observable<SettlementStatus> {
    return this.http.get<SettlementStatus>(`${this.baseUrl}/games/${gameId}/settlement/status`, {
      headers: this.getHeaders()
    });
  }

  repayCredit(gameId: string, userId: number, chipsRepaid: number): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/games/${gameId}/settlement/repay-credit`, {
      user_id: userId,
      chips_repaid: chipsRepaid
    }, { headers: this.getHeaders() });
  }

  completeCreditSettlement(gameId: string): Observable<SettlementStatus> {
    return this.http.post<SettlementStatus>(`${this.baseUrl}/games/${gameId}/settlement/complete-phase1`, {}, {
      headers: this.getHeaders()
    });
  }

  finalCashout(gameId: string, userId: number, chips: number, cashRequested: number, unpaidCreditsClaimed: Array<{debtor_user_id: number; amount: number}>): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/games/${gameId}/settlement/final-cashout`, {
      user_id: userId,
      chips,
      cash_requested: cashRequested,
      unpaid_credits_claimed: unpaidCreditsClaimed
    }, { headers: this.getHeaders() });
  }

  checkSettlementComplete(gameId: string): Observable<{can_complete: boolean; cash_remaining: number; unpaid_credits_remaining: number; message: string}> {
    return this.http.get<{can_complete: boolean; cash_remaining: number; unpaid_credits_remaining: number; message: string}>(`${this.baseUrl}/games/${gameId}/settlement/check-complete`, {
      headers: this.getHeaders()
    });
  }

  completeSettlement(gameId: string): Observable<{success: boolean; message: string}> {
    return this.http.post<{success: boolean; message: string}>(`${this.baseUrl}/games/${gameId}/settlement/complete`, {}, {
      headers: this.getHeaders()
    });
  }

  getPlayerSettlementSummary(gameId: string, userId: number): Observable<SettlementSummary> {
    return this.http.get<SettlementSummary>(`${this.baseUrl}/games/${gameId}/settlement/summary/${userId}`, {
      headers: this.getHeaders()
    });
  }

  getAllSettlementSummaries(gameId: string): Observable<AllSettlementSummaries> {
    return this.http.get<AllSettlementSummaries>(`${this.baseUrl}/games/${gameId}/settlement/summary/all`, {
      headers: this.getHeaders()
    });
  }

  getGameCredits(gameId: string): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/games/${gameId}/credits`, {
      headers: this.getHeaders()
    });
  }

  getSettlementData(gameId: string): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/games/${gameId}/settlement`, {
      headers: this.getHeaders()
    });
  }

  // Host Management Endpoints
  hostBuyin(gameId: string, userId: number, type: string, amount: number): Observable<{ transaction_id: string; message: string }> {
    return this.http.post<{ transaction_id: string; message: string }>(`${this.baseUrl}/games/${gameId}/host-buyin`, {
      user_id: userId,
      type,
      amount
    }, { headers: this.getHeaders() });
  }

  hostCashout(gameId: string, userId: number, amount: number): Observable<{ transaction_id: string; message: string; cashout_breakdown?: any }> {
    return this.http.post<{ transaction_id: string; message: string; cashout_breakdown?: any }>(`${this.baseUrl}/games/${gameId}/host-cashout`, {
      user_id: userId,
      amount
    }, { headers: this.getHeaders() });
  }

  getGameReport(gameId: string): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/games/${gameId}/report`, {
      headers: this.getHeaders()
    });
  }

  // Admin Endpoints
  listAllGames(status?: string): Observable<{ games: Game[] }> {
    let params = new HttpParams();
    if (status) {
      params = params.set('status', status);
    }
    return this.http.get<{ games: Game[] }>(`${this.baseUrl}/admin/games`, {
      headers: this.getHeaders(),
      params
    });
  }

  getSystemStats(): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/admin/stats`, {
      headers: this.getHeaders()
    });
  }

  destroyGame(gameId: string): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(`${this.baseUrl}/admin/games/${gameId}/destroy`, {
      headers: this.getHeaders()
    });
  }
}