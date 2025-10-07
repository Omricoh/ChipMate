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
                <button class="btn btn-success" (click)="showHostBuyin = true">
                  <i class="bi bi-plus-circle me-2"></i>
                  Add Buy-in for Player
                </button>
                <button class="btn btn-warning" (click)="showHostCashout = true">
                  <i class="bi bi-arrow-up-circle me-2"></i>
                  Process Cashout for Player
                </button>
                <button class="btn btn-info" (click)="loadGameReport()">
                  <i class="bi bi-file-earmark-text me-2"></i>
                  Game Report
                </button>
                <button class="btn btn-secondary" (click)="loadSettlement()">
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
                        <small class="text-muted">{{ getTransactionTypeName(tx.type) }} - {{ tx.amount }} chips</small>
                      </div>
                      <span class="badge" [class]="getTransactionBadgeClass(tx.type)">
                        {{ getTransactionTypeName(tx.type) }}
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

    <!-- Host Buy-in Modal -->
    <div class="modal fade" [class.show]="showHostBuyin" [style.display]="showHostBuyin ? 'block' : 'none'" tabindex="-1" *ngIf="showHostBuyin">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="bi bi-plus-circle me-2"></i>
              Add Buy-in for Player
            </h5>
            <button type="button" class="btn-close" (click)="showHostBuyin = false"></button>
          </div>
          <form [formGroup]="hostBuyinForm" (ngSubmit)="submitHostBuyin()">
            <div class="modal-body">
              <div class="mb-3">
                <label class="form-label">Select Player</label>
                <select class="form-control" formControlName="player">
                  <option value="">Choose player...</option>
                  <option *ngFor="let player of getActivePlayers()" [value]="player.user_id">
                    {{ player.name }}
                  </option>
                </select>
              </div>
              <div class="mb-3">
                <label class="form-label">Type</label>
                <select class="form-control" formControlName="type">
                  <option value="cash">Cash</option>
                  <option value="register">Credit</option>
                </select>
              </div>
              <div class="mb-3">
                <label class="form-label">Amount</label>
                <input type="number" class="form-control" formControlName="amount" placeholder="Enter amount" min="1">
              </div>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-secondary" (click)="showHostBuyin = false">Cancel</button>
              <button type="submit" class="btn btn-success" [disabled]="hostBuyinForm.invalid || isLoading">
                <i class="bi bi-check-circle me-1"></i>
                Add Buy-in
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade" [class.show]="showHostBuyin" *ngIf="showHostBuyin" (click)="showHostBuyin = false"></div>

    <!-- Host Cashout Modal -->
    <div class="modal fade" [class.show]="showHostCashout" [style.display]="showHostCashout ? 'block' : 'none'" tabindex="-1" *ngIf="showHostCashout">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="bi bi-arrow-up-circle me-2"></i>
              Process Cashout for Player
            </h5>
            <button type="button" class="btn-close" (click)="showHostCashout = false"></button>
          </div>
          <form [formGroup]="hostCashoutForm" (ngSubmit)="submitHostCashout()">
            <div class="modal-body">
              <div class="mb-3">
                <label class="form-label">Select Player</label>
                <select class="form-control" formControlName="player">
                  <option value="">Choose player...</option>
                  <option *ngFor="let player of getActivePlayers()" [value]="player.user_id">
                    {{ player.name }}
                  </option>
                </select>
              </div>
              <div class="mb-3">
                <label class="form-label">Chip Count</label>
                <input type="number" class="form-control" formControlName="amount" placeholder="Enter chip count" min="1">
              </div>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-secondary" (click)="showHostCashout = false">Cancel</button>
              <button type="submit" class="btn btn-warning" [disabled]="hostCashoutForm.invalid || isLoading">
                <i class="bi bi-check-circle me-1"></i>
                Process Cashout
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade" [class.show]="showHostCashout" *ngIf="showHostCashout" (click)="showHostCashout = false"></div>

    <!-- Game Report Modal -->
    <div class="modal fade" [class.show]="showReport" [style.display]="showReport ? 'block' : 'none'" tabindex="-1" *ngIf="showReport">
      <div class="modal-dialog modal-dialog-centered modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="bi bi-file-earmark-text me-2"></i>
              Game Report - {{ game?.code }}
            </h5>
            <button type="button" class="btn-close" (click)="showReport = false"></button>
          </div>
          <div class="modal-body" *ngIf="gameReport" style="max-height: 70vh; overflow-y: auto;">
            <!-- Game Summary -->
            <div class="card mb-3">
              <div class="card-header bg-primary text-white">
                <h6 class="mb-0">Game Summary</h6>
              </div>
              <div class="card-body">
                <div class="row">
                  <div class="col-6"><strong>Total Players:</strong> {{ gameReport.summary.total_players }}</div>
                  <div class="col-6"><strong>Active Players:</strong> {{ gameReport.summary.active_players }}</div>
                  <div class="col-6"><strong>Total Cash:</strong> {{ gameReport.summary.total_cash }}</div>
                  <div class="col-6"><strong>Total Credit:</strong> {{ gameReport.summary.total_credit }}</div>
                  <div class="col-12 mt-2"><strong>Total Buy-ins:</strong> <span class="text-primary fs-5">{{ gameReport.summary.total_buyins }}</span></div>
                </div>
              </div>
            </div>

            <!-- Player Details -->
            <div class="card mb-3">
              <div class="card-header bg-success text-white">
                <h6 class="mb-0">Player Details</h6>
              </div>
              <div class="card-body">
                <div class="table-responsive">
                  <table class="table table-sm table-striped">
                    <thead>
                      <tr>
                        <th>Player</th>
                        <th>Cash</th>
                        <th>Credit</th>
                        <th>Total</th>
                        <th>Debt</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr *ngFor="let player of gameReport.players">
                        <td>
                          {{ player.name }}
                          <i class="bi bi-crown-fill text-warning ms-1" *ngIf="player.is_host"></i>
                        </td>
                        <td>{{ player.cash_buyins }}</td>
                        <td>{{ player.credit_buyins }}</td>
                        <td><strong>{{ player.total_buyins }}</strong></td>
                        <td class="text-danger">{{ player.pending_debt }}</td>
                        <td>
                          <span class="badge bg-success" *ngIf="player.active && !player.cashed_out">Active</span>
                          <span class="badge bg-info" *ngIf="player.cashed_out">Cashed Out ({{ player.final_chips }})</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <!-- Debt Information -->
            <div class="card mb-3" *ngIf="gameReport.debts && gameReport.debts.length > 0">
              <div class="card-header bg-warning">
                <h6 class="mb-0">Outstanding Debts</h6>
              </div>
              <div class="card-body">
                <div class="table-responsive">
                  <table class="table table-sm table-striped">
                    <thead>
                      <tr>
                        <th>Debtor</th>
                        <th>Creditor</th>
                        <th>Amount</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr *ngFor="let debt of gameReport.debts">
                        <td>{{ debt.debtor_name }}</td>
                        <td>{{ debt.creditor_name || 'Unassigned' }}</td>
                        <td>{{ debt.amount }}</td>
                        <td>
                          <span class="badge" [class]="debt.status === 'pending' ? 'bg-warning' : 'bg-success'">
                            {{ debt.status | titlecase }}
                          </span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" (click)="showReport = false">Close</button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade" [class.show]="showReport" *ngIf="showReport" (click)="showReport = false"></div>

    <!-- Settlement Modal -->
    <div class="modal fade" [class.show]="showSettlement" [style.display]="showSettlement ? 'block' : 'none'" tabindex="-1" *ngIf="showSettlement">
      <div class="modal-dialog modal-dialog-centered modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="bi bi-calculator me-2"></i>
              Settlement - {{ game?.code }}
            </h5>
            <button type="button" class="btn-close" (click)="showSettlement = false"></button>
          </div>
          <div class="modal-body" *ngIf="settlementData" style="max-height: 70vh; overflow-y: auto;">
            <div class="alert alert-info">
              <i class="bi bi-info-circle me-2"></i>
              Settlement shows who owes whom and how cashed-out players received their payouts.
            </div>

            <!-- Cashed Out Players -->
            <div class="card mb-3" *ngIf="settlementData.cashouts && settlementData.cashouts.length > 0">
              <div class="card-header bg-success text-white">
                <h6 class="mb-0">Cashed Out Players</h6>
              </div>
              <div class="card-body">
                <div class="table-responsive">
                  <table class="table table-sm table-striped">
                    <thead>
                      <tr>
                        <th>Player</th>
                        <th>Chips</th>
                        <th>Cash</th>
                        <th>Credit</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr *ngFor="let cashout of settlementData.cashouts">
                        <td>{{ cashout.player_name }}</td>
                        <td>{{ cashout.amount }}</td>
                        <td class="text-success">{{ cashout.cash_component || 0 }}</td>
                        <td class="text-warning">{{ cashout.credit_component || 0 }}</td>
                        <td><span class="badge bg-success">Cashed Out</span></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <!-- Settled Debts -->
            <div class="card mb-3" *ngIf="settlementData.settled_debts && settlementData.settled_debts.length > 0">
              <div class="card-header bg-info text-white">
                <h6 class="mb-0">Settled Debts</h6>
              </div>
              <div class="card-body">
                <div class="table-responsive">
                  <table class="table table-sm table-striped">
                    <thead>
                      <tr>
                        <th>Debtor</th>
                        <th>Creditor</th>
                        <th>Amount</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr *ngFor="let debt of settlementData.settled_debts">
                        <td>{{ debt.debtor_name }}</td>
                        <td>{{ debt.creditor_name }}</td>
                        <td>{{ debt.amount }}</td>
                        <td><span class="badge bg-success">Settled</span></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <!-- No Settlement Data -->
            <div class="alert alert-warning" *ngIf="(!settlementData.cashouts || settlementData.cashouts.length === 0) && (!settlementData.settled_debts || settlementData.settled_debts.length === 0)">
              <i class="bi bi-exclamation-triangle me-2"></i>
              No settlement data available yet. Players need to cash out first.
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" (click)="showSettlement = false">Close</button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade" [class.show]="showSettlement" *ngIf="showSettlement" (click)="showSettlement = false"></div>

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
  currentPlayerUserId: number | null = null;  // The user_id from the Player table
  isHost = false;
  isLoading = false;
  showQrCode = false;
  showSettlement = false;
  showReport = false;
  showHostBuyin = false;
  showHostCashout = false;
  qrCodeDataUrl = '';
  gameJoinUrl = '';
  gameReport: any = null;
  settlementData: any = null;

  // Forms
  buyinForm: FormGroup;
  cashoutForm: FormGroup;
  hostBuyinForm: FormGroup;
  hostCashoutForm: FormGroup;

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

    this.hostBuyinForm = this.formBuilder.group({
      player: ['', [Validators.required]],
      amount: ['', [Validators.required, Validators.min(1)]],
      type: ['cash', [Validators.required]]
    });

    this.hostCashoutForm = this.formBuilder.group({
      player: ['', [Validators.required]],
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
        // Debug: log players
        console.log('Loaded players:', players);

        // Find current player by name match (try both username and name)
        if (this.currentUser) {
          const nameToMatch = this.currentUser.username || this.currentUser.name;
          const currentPlayer = players.find(p => p.name === nameToMatch);
          if (currentPlayer) {
            this.currentPlayerUserId = currentPlayer.user_id;
            console.log('Current player user_id:', this.currentPlayerUserId);

            // Load player summary using the correct user_id
            this.apiService.getPlayerSummary(gameId, this.currentPlayerUserId).subscribe({
              next: (summary) => {
                this.playerSummary = summary;
                console.log('Player summary loaded:', summary);
              },
              error: (error) => {
                console.error('Failed to load player summary:', error);
                // Set empty summary to show the card
                this.playerSummary = {
                  cash_buyins: 0,
                  credit_buyins: 0,
                  total_buyins: 0,
                  pending_debt: 0,
                  transactions: []
                };
              }
            });
          } else {
            const attemptedName = this.currentUser.username || this.currentUser.name;
            console.warn('Current player not found in players list. Name:', attemptedName, 'Available players:', players.map(p => p.name));
            this.showError(`Player "${attemptedName}" not found in game. Please rejoin the game.`);
          }
        } else {
          console.warn('No current user logged in');
        }
      }
    });

    // Load pending transactions (if host)
    if (this.isHost) {
      this.apiService.getPendingTransactions(gameId).subscribe({
        next: (transactions) => {
          this.pendingTransactions = transactions;
          // Debug: log transactions
          console.log('Pending transactions:', transactions);
        },
        error: (error) => {
          console.error('Failed to load pending transactions:', error);
          this.pendingTransactions = [];
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
    if (!this.currentPlayerUserId) {
      this.showError('Cannot submit buy-in. Player not found in game. Please refresh or rejoin.');
      console.error('submitBuyin failed: currentPlayerUserId is null');
      return;
    }

    if (this.buyinForm.valid && this.game && this.currentPlayerUserId) {
      this.isLoading = true;

      const buyinRequest = {
        game_id: this.game.id,
        user_id: this.currentPlayerUserId,
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
    if (!this.currentPlayerUserId) {
      this.showError('Cannot submit cashout. Player not found in game. Please refresh or rejoin.');
      console.error('submitCashout failed: currentPlayerUserId is null');
      return;
    }

    if (this.cashoutForm.valid && this.game && this.currentPlayerUserId) {
      this.isLoading = true;

      const cashoutRequest = {
        game_id: this.game.id,
        user_id: this.currentPlayerUserId,
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
    // Try to find player by user_id with type conversion
    const player = this.players.find(p => p.user_id == userId); // Use == for loose comparison
    if (player) {
      return player.name;
    }
    // If not found, log for debugging
    console.warn(`Player not found for user_id: ${userId}`, 'Available players:', this.players);
    return 'Unknown Player';
  }

  getTransactionTypeName(type: string): string {
    // Format transaction type for display
    if (!type) return 'Unknown';

    // Remove 'buyin_' prefix if present
    const cleanType = type.replace('buyin_', '');

    // Convert to readable format
    switch (cleanType) {
      case 'cash':
        return 'Cash Buy-in';
      case 'register':
        return 'Credit Buy-in';
      case 'cashout':
        return 'Cashout';
      default:
        // Fallback to title case
        return cleanType.charAt(0).toUpperCase() + cleanType.slice(1);
    }
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

  // Host Management Methods
  submitHostBuyin(): void {
    if (this.hostBuyinForm.valid && this.game) {
      this.isLoading = true;
      const userId = parseInt(this.hostBuyinForm.value.player, 10);
      const amount = parseInt(this.hostBuyinForm.value.amount, 10);
      const type = this.hostBuyinForm.value.type;

      this.apiService.hostBuyin(this.game.id, userId, type, amount).subscribe({
        next: (response) => {
          this.isLoading = false;
          this.hostBuyinForm.reset({ type: 'cash' });
          this.showHostBuyin = false;
          this.showSuccess('Buy-in added successfully');
          this.refreshData();
        },
        error: (error) => {
          this.isLoading = false;
          this.showError(error.error?.message || 'Failed to add buy-in');
        }
      });
    }
  }

  submitHostCashout(): void {
    if (this.hostCashoutForm.valid && this.game) {
      this.isLoading = true;
      const userId = parseInt(this.hostCashoutForm.value.player, 10);
      const amount = parseInt(this.hostCashoutForm.value.amount, 10);

      this.apiService.hostCashout(this.game.id, userId, amount).subscribe({
        next: (response) => {
          this.isLoading = false;
          this.hostCashoutForm.reset();
          this.showHostCashout = false;
          this.showSuccess('Cashout processed successfully');
          this.refreshData();
        },
        error: (error) => {
          this.isLoading = false;
          this.showError(error.error?.message || 'Failed to process cashout');
        }
      });
    }
  }

  loadGameReport(): void {
    if (this.game) {
      this.apiService.getGameReport(this.game.id).subscribe({
        next: (report) => {
          this.gameReport = report;
          this.showReport = true;
        },
        error: (error) => {
          this.showError('Failed to load game report');
        }
      });
    }
  }

  loadSettlement(): void {
    if (this.game) {
      this.apiService.getSettlementData(this.game.id).subscribe({
        next: (data) => {
          this.settlementData = data;
          this.showSettlement = true;
        },
        error: (error) => {
          this.showError('Failed to load settlement data');
        }
      });
    }
  }

  getActivePlayers(): Player[] {
    return this.players.filter(p => p.active && !p.quit);
  }
}