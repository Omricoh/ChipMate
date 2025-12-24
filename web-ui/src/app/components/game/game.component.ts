import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { QrCodeService } from '../../services/qr-code.service';
import { Game, GameStatus, Player, Transaction, PlayerSummary } from '../../models/game.model';
import { User } from '../../models/user.model';
import { Subscription, interval } from 'rxjs';

@Component({
  selector: 'app-game',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  template: `
    <div class="container-fluid mt-4" *ngIf="game">
      <!-- Game Header -->
      <div class="row mb-4">
        <div class="col-12">
          <div class="card game-card">
            <div class="card-header d-flex justify-content-between align-items-center">
              <div>
                <h4 class="mb-0">
                  <i class="bi bi-suit-spade-fill me-2"></i>
                  Game {{ game.code }}
                </h4>
                <small class="text-light">
                  Host: {{ game.host_name }} |
                  <span [class]="getStatusClass(game.status)">{{ game.status | titlecase }}</span>
                </small>
              </div>
              <div class="d-flex gap-2">
                <button class="btn btn-outline-light btn-sm" (click)="onShowQrCode()" *ngIf="isHost">
                  <i class="bi bi-qr-code me-1"></i>
                  QR Code
                </button>
                <button class="btn btn-outline-light btn-sm" (click)="refreshData()">
                  <i class="bi bi-arrow-clockwise me-1"></i>
                  Refresh
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="row">
        <!-- Left Column - Player Actions -->
        <div class="col-lg-4">
          <!-- Player Status Card -->
          <div class="card game-card mb-4" *ngIf="playerSummary">
            <div class="card-header">
              <h6 class="mb-0">
                <i class="bi bi-person-circle me-2"></i>
                Your Status
              </h6>
            </div>
            <div class="card-body">
              <div class="row text-center">
                <div class="col-6">
                  <div class="mb-2">
                    <i class="bi bi-cash text-success" style="font-size: 1.5rem;"></i>
                  </div>
                  <h6>Cash Buy-ins</h6>
                  <span class="badge bg-success">{{ playerSummary.cash_buyins }}</span>
                </div>
                <div class="col-6">
                  <div class="mb-2">
                    <i class="bi bi-credit-card text-warning" style="font-size: 1.5rem;"></i>
                  </div>
                  <h6>Credit Buy-ins</h6>
                  <span class="badge bg-warning">{{ playerSummary.credit_buyins }}</span>
                </div>
              </div>
              <hr>
              <div class="row text-center">
                <div class="col-6">
                  <h6>Total Investment</h6>
                  <span class="badge bg-primary">{{ playerSummary.total_buyins }}</span>
                </div>
                <div class="col-6">
                  <h6>Pending Debt</h6>
                  <span class="badge bg-danger">{{ playerSummary.pending_debt }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Player Actions Card -->
          <div class="card game-card mb-4" *ngIf="!isHost && game.status === 'active'">
            <div class="card-header">
              <h6 class="mb-0">
                <i class="bi bi-lightning-fill me-2"></i>
                Player Actions
              </h6>
            </div>
            <div class="card-body">
              <!-- Buy-in Form -->
              <form [formGroup]="buyinForm" (ngSubmit)="submitBuyin()" class="mb-3">
                <h6>Buy-in</h6>
                <div class="row g-2 mb-2">
                  <div class="col-8">
                    <input type="number" class="form-control" formControlName="amount" placeholder="Amount" min="1">
                  </div>
                  <div class="col-4">
                    <select class="form-control" formControlName="type">
                      <option value="cash">Cash</option>
                      <option value="register">Credit</option>
                    </select>
                  </div>
                </div>
                <button type="submit" class="btn btn-success w-100" [disabled]="buyinForm.invalid || isLoading">
                  <i class="bi bi-plus-circle me-1"></i>
                  Buy-in
                </button>
              </form>

              <!-- Cashout Form -->
              <form [formGroup]="cashoutForm" (ngSubmit)="submitCashout()">
                <h6>Cashout</h6>
                <div class="mb-2">
                  <input type="number" class="form-control" formControlName="amount" placeholder="Chip count" min="1">
                </div>
                <button type="submit" class="btn btn-warning w-100" [disabled]="cashoutForm.invalid || isLoading">
                  <i class="bi bi-arrow-up-right-circle me-1"></i>
                  Request Cashout
                </button>
              </form>
            </div>
          </div>

          <!-- My Transactions Card -->
          <div class="card game-card mb-4" *ngIf="playerSummary && playerSummary.transactions.length > 0">
            <div class="card-header">
              <h6 class="mb-0">
                <i class="bi bi-receipt me-2"></i>
                My Transactions ({{ playerSummary.transactions.length }})
              </h6>
            </div>
            <div class="card-body">
              <div class="transaction-history" style="max-height: 300px; overflow-y: auto;">
                <div class="mb-2 pb-2 border-bottom" *ngFor="let tx of playerSummary.transactions">
                  <div class="d-flex justify-content-between align-items-start">
                    <div>
                      <span class="badge me-1" [class]="getTransactionBadgeClass(tx.type)">
                        {{ formatTransactionType(tx.type) }}
                      </span>
                      <strong>{{ tx.amount }}</strong> chips
                    </div>
                  </div>
                  <small class="text-muted">
                    <i class="bi bi-clock me-1"></i>
                    {{ formatTransactionDate(tx.created_at) }}
                  </small>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Middle Column - Game Status -->
        <div class="col-lg-4">
          <!-- Game Overview Card -->
          <div class="card game-card mb-4" *ngIf="gameStatus">
            <div class="card-header">
              <h6 class="mb-0">
                <i class="bi bi-graph-up me-2"></i>
                Game Overview
              </h6>
            </div>
            <div class="card-body">
              <div class="row text-center">
                <div class="col-4">
                  <div class="mb-2">
                    <i class="bi bi-people text-primary" style="font-size: 1.5rem;"></i>
                  </div>
                  <h6>Players</h6>
                  <span class="badge bg-primary">{{ gameStatus.active_players }}</span>
                </div>
                <div class="col-4">
                  <div class="mb-2">
                    <i class="bi bi-cash-stack text-success" style="font-size: 1.5rem;"></i>
                  </div>
                  <h6>Total Cash</h6>
                  <span class="badge bg-success">{{ gameStatus.total_cash }}</span>
                </div>
                <div class="col-4">
                  <div class="mb-2">
                    <i class="bi bi-credit-card text-warning" style="font-size: 1.5rem;"></i>
                  </div>
                  <h6>Total Credit</h6>
                  <span class="badge bg-warning">{{ gameStatus.total_credit }}</span>
                </div>
              </div>
              <hr>
              <div class="text-center">
                <h6>Money in Play</h6>
                <h4 class="text-primary">{{ gameStatus.total_buyins }}</h4>
              </div>
            </div>
          </div>

          <!-- Players List Card -->
          <div class="card game-card mb-4" *ngIf="players.length > 0">
            <div class="card-header">
              <h6 class="mb-0">
                <i class="bi bi-people-fill me-2"></i>
                Players ({{ players.length }})
              </h6>
            </div>
            <div class="card-body">
              <div class="player-list" style="max-height: 300px; overflow-y: auto;">
                <div class="d-flex justify-content-between align-items-center mb-2" *ngFor="let player of players">
                  <div class="d-flex align-items-center">
                    <i class="bi bi-crown-fill text-warning me-2" *ngIf="player.is_host"></i>
                    <i class="bi bi-person-circle me-2" *ngIf="!player.is_host"></i>
                    <span [class.fw-bold]="player.is_host">{{ player.name }}</span>
                  </div>
                  <div>
                    <span class="badge bg-success me-1" *ngIf="player.active && !player.quit">Active</span>
                    <span class="badge bg-secondary me-1" *ngIf="player.quit">Quit</span>
                    <span class="badge bg-info" *ngIf="player.cashed_out">Cashed Out</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Right Column - Host Actions / Pending Transactions -->
        <div class="col-lg-4">
          <!-- Host Actions Card -->
          <div class="card game-card mb-4" *ngIf="isHost && game.status === 'active'">
            <div class="card-header">
              <h6 class="mb-0">
                <i class="bi bi-shield-check me-2"></i>
                Host Actions
              </h6>
            </div>
            <div class="card-body">
              <div class="d-grid gap-2">
                <button class="btn btn-info" (click)="showSettlement = true">
                  <i class="bi bi-calculator me-2"></i>
                  View Settlement
                </button>
                <button class="btn btn-danger" (click)="confirmEndGame()">
                  <i class="bi bi-stop-circle me-2"></i>
                  End Game
                </button>
              </div>
            </div>
          </div>

          <!-- Pending Transactions Card -->
          <div class="card game-card mb-4" *ngIf="isHost && pendingTransactions.length > 0">
            <div class="card-header">
              <h6 class="mb-0">
                <i class="bi bi-clock-history me-2"></i>
                Pending Approvals ({{ pendingTransactions.length }})
              </h6>
            </div>
            <div class="card-body">
              <div class="transaction-list" style="max-height: 400px; overflow-y: auto;">
                <div class="card mb-2" *ngFor="let tx of pendingTransactions">
                  <div class="card-body p-2">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                      <div>
                        <strong>{{ getPlayerName(tx.user_id) }}</strong>
                        <br>
                        <small class="text-muted">{{ tx.type | titlecase }} - {{ tx.amount }} chips</small>
                      </div>
                      <span class="badge" [class]="getTransactionBadgeClass(tx.type)">
                        {{ tx.type | titlecase }}
                      </span>
                    </div>
                    <div class="d-grid gap-1">
                      <button class="btn btn-success btn-sm" (click)="approveTransaction(tx.id)">
                        <i class="bi bi-check-circle me-1"></i>
                        Approve
                      </button>
                      <button class="btn btn-outline-danger btn-sm" (click)="rejectTransaction(tx.id)">
                        <i class="bi bi-x-circle me-1"></i>
                        Reject
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- QR Code Modal -->
    <div class="modal fade" [class.show]="showQrCode" [style.display]="showQrCode ? 'block' : 'none'" tabindex="-1" *ngIf="showQrCode">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="bi bi-qr-code me-2"></i>
              Share Game - {{ game?.code }}
            </h5>
            <button type="button" class="btn-close" (click)="showQrCode = false"></button>
          </div>
          <div class="modal-body text-center">
            <div class="qr-container" *ngIf="qrCodeDataUrl">
              <img [src]="qrCodeDataUrl" alt="Game QR Code" class="img-fluid mb-3" style="max-width: 300px;">
              <p class="mb-2"><strong>Game Code: {{ game?.code }}</strong></p>
              <p class="text-muted">Players can scan this QR code or use the game code to join</p>
              <div class="mt-3">
                <input type="text" class="form-control text-center" [value]="gameJoinUrl" readonly (click)="copyToClipboard(gameJoinUrl)">
                <small class="text-muted">Click to copy join link</small>
              </div>
            </div>
            <div *ngIf="!qrCodeDataUrl" class="text-center">
              <div class="loading-spinner"></div>
              <p class="mt-2">Generating QR code...</p>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade" [class.show]="showQrCode" *ngIf="showQrCode" (click)="showQrCode = false"></div>

    <!-- Messages -->
    <div class="position-fixed top-0 end-0 p-3" style="z-index: 11">
      <div class="toast align-items-center text-white bg-success border-0" [class.show]="showSuccessToast" role="alert">
        <div class="d-flex">
          <div class="toast-body">
            {{ successMessage }}
          </div>
          <button type="button" class="btn-close btn-close-white me-2 m-auto" (click)="showSuccessToast = false"></button>
        </div>
      </div>
      <div class="toast align-items-center text-white bg-danger border-0" [class.show]="showErrorToast" role="alert">
        <div class="d-flex">
          <div class="toast-body">
            {{ errorMessage }}
          </div>
          <button type="button" class="btn-close btn-close-white me-2 m-auto" (click)="showErrorToast = false"></button>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .modal {
      background-color: rgba(0,0,0,0.5);
    }
    .toast.show {
      display: block !important;
    }
  `]
})
export class GameComponent implements OnInit, OnDestroy {
  game: Game | null = null;
  gameStatus: GameStatus | null = null;
  players: Player[] = [];
  pendingTransactions: Transaction[] = [];
  playerSummary: PlayerSummary | null = null;
  currentUser: User | null = null;
  isHost = false;
  isLoading = false;
  showQrCode = false;
  showSettlement = false;
  qrCodeDataUrl = '';
  gameJoinUrl = '';

  // Forms
  buyinForm: FormGroup;
  cashoutForm: FormGroup;

  // Messages
  successMessage = '';
  errorMessage = '';
  showSuccessToast = false;
  showErrorToast = false;

  // Subscriptions
  private refreshSubscription: Subscription | null = null;

  constructor(
    private apiService: ApiService,
    private qrCodeService: QrCodeService,
    private formBuilder: FormBuilder,
    private route: ActivatedRoute,
    private router: Router
  ) {
    this.buyinForm = this.formBuilder.group({
      amount: ['', [Validators.required, Validators.min(1)]],
      type: ['cash', [Validators.required]]
    });

    this.cashoutForm = this.formBuilder.group({
      amount: ['', [Validators.required, Validators.min(1)]]
    });

    this.currentUser = this.apiService.getCurrentUser();
  }

  ngOnInit(): void {
    this.route.params.subscribe(params => {
      if (params['gameId']) {
        this.loadGameData(params['gameId']);
        this.startAutoRefresh();
      }
    });
  }

  ngOnDestroy(): void {
    if (this.refreshSubscription) {
      this.refreshSubscription.unsubscribe();
    }
  }

  loadGameData(gameId: string): void {
    // Load game details
    this.apiService.getGame(gameId).subscribe({
      next: (game) => {
        this.game = game;
        this.isHost = this.currentUser?.is_host || false;
        this.gameJoinUrl = `${window.location.origin}/join/${game.code}`;
      },
      error: (error) => {
        this.showError('Failed to load game details');
        this.router.navigate(['/home']);
      }
    });

    // Load game status
    this.apiService.getGameStatus(gameId).subscribe({
      next: (status) => {
        this.gameStatus = status;
      }
    });

    // Load players
    this.apiService.getGamePlayers(gameId).subscribe({
      next: (players) => {
        this.players = players;
      }
    });

    // Load pending transactions (if host)
    if (this.isHost) {
      this.apiService.getPendingTransactions(gameId).subscribe({
        next: (transactions) => {
          this.pendingTransactions = transactions;
        }
      });
    }

    // Load player summary
    if (this.currentUser) {
      this.apiService.getPlayerSummary(gameId, this.currentUser.id).subscribe({
        next: (summary) => {
          this.playerSummary = summary;
        }
      });
    }
  }

  startAutoRefresh(): void {
    this.refreshSubscription = interval(10000).subscribe(() => {
      if (this.game) {
        this.refreshData();
      }
    });
  }

  refreshData(): void {
    if (this.game) {
      this.loadGameData(this.game.id);
    }
  }

  async generateQrCode(): Promise<void> {
    if (this.game) {
      try {
        this.qrCodeDataUrl = await this.qrCodeService.generateGameJoinQR(this.game.code);
      } catch (error) {
        this.showError('Failed to generate QR code');
      }
    }
  }

  submitBuyin(): void {
    if (this.buyinForm.valid && this.game && this.currentUser) {
      this.isLoading = true;

      const buyinRequest = {
        game_id: this.game.id,
        user_id: this.currentUser.id,
        type: this.buyinForm.value.type,
        amount: parseInt(this.buyinForm.value.amount, 10)
      };

      this.apiService.createBuyin(buyinRequest).subscribe({
        next: (response) => {
          this.isLoading = false;
          this.buyinForm.reset({ type: 'cash' });
          this.showSuccess('Buy-in request submitted for approval');
          this.refreshData();
        },
        error: (error) => {
          this.isLoading = false;
          this.showError(error.error?.message || 'Failed to submit buy-in');
        }
      });
    }
  }

  submitCashout(): void {
    if (this.cashoutForm.valid && this.game && this.currentUser) {
      this.isLoading = true;

      const cashoutRequest = {
        game_id: this.game.id,
        user_id: this.currentUser.id,
        amount: parseInt(this.cashoutForm.value.amount, 10)
      };

      this.apiService.createCashout(cashoutRequest).subscribe({
        next: (response) => {
          this.isLoading = false;
          this.cashoutForm.reset();
          this.showSuccess('Cashout request submitted for approval');
          this.refreshData();
        },
        error: (error) => {
          this.isLoading = false;
          this.showError(error.error?.message || 'Failed to submit cashout');
        }
      });
    }
  }

  approveTransaction(transactionId: string): void {
    this.apiService.approveTransaction(transactionId).subscribe({
      next: (response) => {
        this.showSuccess('Transaction approved');
        this.refreshData();
      },
      error: (error) => {
        this.showError(error.error?.message || 'Failed to approve transaction');
      }
    });
  }

  rejectTransaction(transactionId: string): void {
    this.apiService.rejectTransaction(transactionId).subscribe({
      next: (response) => {
        this.showSuccess('Transaction rejected');
        this.refreshData();
      },
      error: (error) => {
        this.showError(error.error?.message || 'Failed to reject transaction');
      }
    });
  }

  confirmEndGame(): void {
    if (confirm('Are you sure you want to end this game? This cannot be undone.')) {
      if (this.game) {
        this.apiService.endGame(this.game.id).subscribe({
          next: (response) => {
            this.showSuccess('Game ended successfully');
            this.refreshData();
          },
          error: (error) => {
            this.showError(error.error?.message || 'Failed to end game');
          }
        });
      }
    }
  }

  async onShowQrCode(): Promise<void> {
    this.showQrCode = true;
    if (!this.qrCodeDataUrl) {
      await this.generateQrCode();
    }
  }

  copyToClipboard(text: string): void {
    navigator.clipboard.writeText(text).then(() => {
      this.showSuccess('Link copied to clipboard!');
    });
  }

  getPlayerName(userId: number): string {
    const player = this.players.find(p => p.user_id === userId);
    return player ? player.name : 'Unknown Player';
  }

  getStatusClass(status: string): string {
    switch (status) {
      case 'active': return 'status-active';
      case 'ended': return 'status-ended';
      case 'expired': return 'status-expired';
      default: return '';
    }
  }

  getTransactionBadgeClass(type: string): string {
    switch (type) {
      case 'buyin_cash': return 'bg-success';
      case 'buyin_register': return 'bg-warning';
      case 'cashout': return 'bg-info';
      default: return 'bg-secondary';
    }
  }

  formatTransactionType(type: string): string {
    switch (type) {
      case 'buyin_cash': return 'Cash Buy-in';
      case 'buyin_register': return 'Credit Buy-in';
      case 'cashout': return 'Cashout';
      default: return type;
    }
  }

  formatTransactionDate(dateString: string): string {
    if (!dateString) return 'N/A';
    
    const date = new Date(dateString);
    // Validate the date
    if (isNaN(date.getTime())) return 'Invalid date';
    
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);

    // Format: "Today at 3:45 PM" or "Yesterday at 3:45 PM" or "Dec 24 at 3:45 PM"
    const timeStr = date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    
    // Check if same day (comparing date strings to handle timezone properly)
    const dateStr = date.toDateString();
    const nowStr = now.toDateString();
    const MS_PER_DAY = 24 * 60 * 60 * 1000;
    const yesterdayStr = new Date(now.getTime() - MS_PER_DAY).toDateString();
    
    if (diffMins < 1) {
      return 'Just now';
    } else if (diffMins < 60) {
      return `${diffMins} min${diffMins > 1 ? 's' : ''} ago`;
    } else if (dateStr === nowStr) {
      return `Today at ${timeStr}`;
    } else if (dateStr === yesterdayStr) {
      return `Yesterday at ${timeStr}`;
    } else if (diffHours < 168) { // Less than 7 days
      // Calculate days based on date strings, not hours, to avoid overlap with "Yesterday"
      const diffDays = Math.floor(diffMs / MS_PER_DAY);
      if (diffDays >= 2 && diffDays < 7) {
        return `${diffDays} day${diffDays > 1 ? 's' : ''} ago at ${timeStr}`;
      }
      // If between 1 and 2 days but not yesterday, fall through to general format
      const monthDay = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      return `${monthDay} at ${timeStr}`;
    } else {
      const monthDay = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      return `${monthDay} at ${timeStr}`;
    }
  }

  showSuccess(message: string): void {
    this.successMessage = message;
    this.showSuccessToast = true;
    setTimeout(() => {
      this.showSuccessToast = false;
    }, 5000);
  }

  showError(message: string): void {
    this.errorMessage = message;
    this.showErrorToast = true;
    setTimeout(() => {
      this.showErrorToast = false;
    }, 5000);
  }
}