import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { QrCodeService } from '../../services/qr-code.service';
import { Game, GameStatus, Player, Transaction, PlayerSummary, SettlementStatus, SettlementSummary, AllSettlementSummaries, UnpaidCredit, BankStatus } from '../../models/game.model';
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

      <!-- Bank Status Card (Host Only) -->
      <div class="row mb-4" *ngIf="isHost && bankStatus">
        <div class="col-12">
          <div class="card game-card">
            <div class="card-header">
              <h6 class="mb-0">
                <i class="bi bi-bank me-2"></i>
                Bank Status
              </h6>
            </div>
            <div class="card-body">
              <div class="row text-center">
                <div class="col-md-3 col-6 mb-3">
                  <div class="mb-2">
                    <i class="bi bi-cash-stack text-success" style="font-size: 1.5rem;"></i>
                  </div>
                  <h6>Cash Balance</h6>
                  <span class="badge bg-success fs-6">{{ bankStatus.cash_balance }}</span>
                </div>
                <div class="col-md-3 col-6 mb-3">
                  <div class="mb-2">
                    <i class="bi bi-wallet2 text-info" style="font-size: 1.5rem;"></i>
                  </div>
                  <h6>Available Cash</h6>
                  <span class="badge bg-info fs-6">{{ bankStatus.available_cash }}</span>
                </div>
                <div class="col-md-3 col-6 mb-3">
                  <div class="mb-2">
                    <i class="bi bi-exclamation-triangle text-warning" style="font-size: 1.5rem;"></i>
                  </div>
                  <h6>Outstanding Credits</h6>
                  <span class="badge bg-warning fs-6">{{ bankStatus.outstanding_credits }}</span>
                </div>
                <div class="col-md-3 col-6 mb-3">
                  <div class="mb-2">
                    <i class="bi bi-disc text-primary" style="font-size: 1.5rem;"></i>
                  </div>
                  <h6>Chips in Play</h6>
                  <span class="badge bg-primary fs-6">{{ bankStatus.chips_in_play }}</span>
                </div>
              </div>
              <hr>
              <div class="row text-center">
                <div class="col-md-3 col-6">
                  <h6>Total Cash In</h6>
                  <span class="badge bg-success">{{ bankStatus.total_cash_in }}</span>
                </div>
                <div class="col-md-3 col-6">
                  <h6>Total Cash Out</h6>
                  <span class="badge bg-secondary">{{ bankStatus.total_cash_out }}</span>
                </div>
                <div class="col-md-3 col-6">
                  <h6>Total Credits Issued</h6>
                  <span class="badge bg-warning">{{ bankStatus.total_credits_issued }}</span>
                </div>
                <div class="col-md-3 col-6">
                  <h6>Total Credits Repaid</h6>
                  <span class="badge bg-info">{{ bankStatus.total_credits_repaid }}</span>
                </div>
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
                  <h6>Credits Owed</h6>
                  <span class="badge bg-danger">{{ playerSummary.credits_owed }}</span>
                </div>
              </div>

              <!-- Show transaction history throughout the game -->
              <div *ngIf="playerSummary.transactions && playerSummary.transactions.length > 0">
                <hr>
                <h6 class="mb-2">
                  <i class="bi bi-list-ul me-2"></i>
                  Your Transactions
                </h6>
                <div style="max-height: 300px; overflow-y: auto;">
                  <table class="table table-sm">
                    <thead>
                      <tr>
                        <th>Date/Time</th>
                        <th>Type</th>
                        <th>Amount</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr *ngFor="let tx of playerSummary.transactions">
                        <td class="text-muted small">{{ formatTransactionDate(tx.at) }}</td>
                        <td>
                          <span *ngIf="tx.type === 'buyin_cash'" class="badge bg-success">Cash</span>
                          <span *ngIf="tx.type === 'buyin_register'" class="badge bg-warning">Credit</span>
                          <span *ngIf="tx.type === 'cashout'" class="badge bg-info">Cashout</span>
                        </td>
                        <td>{{ tx.amount }}</td>
                        <td>
                          <span *ngIf="tx.confirmed" class="badge bg-success">
                            <i class="bi bi-check-circle"></i>
                          </span>
                          <span *ngIf="tx.rejected" class="badge bg-danger">
                            <i class="bi bi-x-circle"></i>
                          </span>
                          <span *ngIf="!tx.confirmed && !tx.rejected" class="badge bg-secondary">Pending</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>

          <!-- Player Actions Card -->
          <div class="card game-card mb-4" *ngIf="!isHost && game.status === 'active' && !isCurrentPlayerInactive()">
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
                <div class="mb-2">
                  <input type="number" class="form-control" formControlName="amount" placeholder="Amount" min="1">
                </div>
                <div class="mb-2">
                  <div class="form-check">
                    <input class="form-check-input" type="radio" formControlName="type" value="cash" id="typeCash">
                    <label class="form-check-label" for="typeCash">
                      <i class="bi bi-cash text-success me-1"></i>
                      Cash
                    </label>
                  </div>
                  <div class="form-check">
                    <input class="form-check-input" type="radio" formControlName="type" value="register" id="typeCredit">
                    <label class="form-check-label" for="typeCredit">
                      <i class="bi bi-credit-card text-warning me-1"></i>
                      Credit
                    </label>
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
                  <input type="number" class="form-control" formControlName="amount" placeholder="Chip count (0 if lost all)" min="0">
                </div>
                <button type="submit" class="btn btn-warning w-100" [disabled]="cashoutForm.invalid || isLoading">
                  <i class="bi bi-arrow-up-right-circle me-1"></i>
                  Request Cashout
                </button>
              </form>
            </div>
          </div>

          <!-- Inactive Player Card -->
          <div class="card game-card mb-4" *ngIf="!isHost && game.status === 'active' && isCurrentPlayerInactive()">
            <div class="card-header bg-warning">
              <h6 class="mb-0">
                <i class="bi bi-info-circle me-2"></i>
                Player Status
              </h6>
            </div>
            <div class="card-body">
              <div class="alert alert-warning mb-3">
                <strong>You have cashed out and are now inactive</strong>
                <p class="mb-0 mt-2">You can view your transaction history below, but cannot create new buyins or cashouts.</p>
              </div>
            </div>
          </div>

          <!-- Player Settlement Summary Card -->
          <div class="card game-card mb-4" *ngIf="!isHost && (game.status === 'ending' || game.status === 'settled') && playerSettlementSummary">
            <div class="card-header">
              <h6 class="mb-0">
                <i class="bi bi-file-text me-2"></i>
                Your Settlement Summary
              </h6>
            </div>
            <div class="card-body">
              <!-- Player Totals -->
              <div class="mb-3">
                <h6 class="text-muted mb-2">Your Totals</h6>
                <div class="row g-2">
                  <div class="col-6">
                    <small class="text-muted">Cash Buy-ins:</small>
                    <div class="fw-bold text-success">{{ playerSettlementSummary.totals.cash_buyins }}</div>
                  </div>
                  <div class="col-6">
                    <small class="text-muted">Credit Buy-ins:</small>
                    <div class="fw-bold text-warning">{{ playerSettlementSummary.totals.credit_buyins }}</div>
                  </div>
                  <div class="col-6">
                    <small class="text-muted">Cashouts:</small>
                    <div class="fw-bold">{{ playerSettlementSummary.totals.cashouts }}</div>
                  </div>
                  <div class="col-6">
                    <small class="text-muted">Net:</small>
                    <div class="fw-bold" [class.text-success]="playerSettlementSummary.totals.net >= 0" [class.text-danger]="playerSettlementSummary.totals.net < 0">
                      {{ playerSettlementSummary.totals.net > 0 ? '+' : '' }}{{ playerSettlementSummary.totals.net }}
                    </div>
                  </div>
                </div>
              </div>

              <!-- Who Owes You -->
              <div class="mb-3" *ngIf="playerSettlementSummary.owes_to_me && playerSettlementSummary.owes_to_me.length > 0">
                <h6 class="text-muted mb-2">Who Owes You</h6>
                <div class="list-group list-group-flush">
                  <div class="list-group-item px-0 py-2 d-flex justify-content-between align-items-center" *ngFor="let debt of playerSettlementSummary.owes_to_me">
                    <span>{{ debt.debtor_name }}</span>
                    <span class="badge bg-warning">{{ debt.amount }}</span>
                  </div>
                </div>
              </div>
              <div class="mb-3" *ngIf="!playerSettlementSummary.owes_to_me || playerSettlementSummary.owes_to_me.length === 0">
                <h6 class="text-muted mb-2">Who Owes You</h6>
                <p class="text-muted small mb-0">No one owes you money</p>
              </div>

              <!-- What You Owe -->
              <div class="mb-3" *ngIf="playerSettlementSummary.i_owe && playerSettlementSummary.i_owe.length > 0">
                <h6 class="text-muted mb-2">What You Owe</h6>
                <div class="list-group list-group-flush">
                  <div class="list-group-item px-0 py-2 d-flex justify-content-between align-items-center" *ngFor="let owed of playerSettlementSummary.i_owe">
                    <span class="small">{{ owed.note }}</span>
                    <span class="badge bg-danger">{{ owed.amount }}</span>
                  </div>
                </div>
              </div>
              <div class="mb-3" *ngIf="!playerSettlementSummary.i_owe || playerSettlementSummary.i_owe.length === 0">
                <h6 class="text-muted mb-2">What You Owe</h6>
                <p class="text-muted small mb-0">You don't owe anything</p>
              </div>

              <!-- Transaction History -->
              <div *ngIf="playerSettlementSummary.transactions && playerSettlementSummary.transactions.length > 0">
                <h6 class="text-muted mb-2">Your Transactions</h6>
                <div style="max-height: 200px; overflow-y: auto;">
                  <table class="table table-sm">
                    <thead>
                      <tr>
                        <th>Date/Time</th>
                        <th>Type</th>
                        <th>Amount</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr *ngFor="let tx of playerSettlementSummary.transactions">
                        <td class="text-muted small">{{ formatTransactionDate(tx.at) }}</td>
                        <td>
                          <span *ngIf="tx.type === 'buyin_cash'" class="badge bg-success">Cash</span>
                          <span *ngIf="tx.type === 'buyin_register'" class="badge bg-warning">Credit</span>
                          <span *ngIf="tx.type === 'cashout'" class="badge bg-info">Cashout</span>
                        </td>
                        <td>{{ tx.amount }}</td>
                        <td>
                          <span *ngIf="tx.confirmed" class="badge bg-success">✓</span>
                          <span *ngIf="tx.rejected" class="badge bg-danger">✗</span>
                          <span *ngIf="!tx.confirmed && !tx.rejected" class="badge bg-secondary">Pending</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
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
                    <span class="badge bg-info" *ngIf="player.cashed_out">
                      Cashed Out ({{ player.final_chips || 0 }} chips)
                    </span>
                    <span class="badge bg-success" *ngIf="!player.cashed_out && player.active && !player.quit">Active</span>
                    <span class="badge bg-secondary" *ngIf="!player.cashed_out && player.quit">Quit</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Right Column - Host Actions / Pending Transactions -->
        <div class="col-lg-4">
          <!-- Host Actions Card -->
          <div class="card game-card mb-4" *ngIf="isHost && (game.status === 'active' || game.status === 'ending' || game.status === 'settled')">
            <div class="card-header">
              <h6 class="mb-0">
                <i class="bi bi-shield-check me-2"></i>
                Host Actions
              </h6>
            </div>
            <div class="card-body">
              <div class="d-grid gap-2">
                <button class="btn btn-success" (click)="showHostBuyin = true" *ngIf="game.status === 'active'">
                  <i class="bi bi-plus-circle me-2"></i>
                  Add Buy-in for Player
                </button>
                <button class="btn btn-warning" (click)="showHostCashout = true" *ngIf="game.status === 'active'">
                  <i class="bi bi-arrow-up-circle me-2"></i>
                  Process Cashout for Player
                </button>
                <button class="btn btn-info" (click)="loadGameReport()">
                  <i class="bi bi-file-earmark-text me-2"></i>
                  Game Report
                </button>
                <button class="btn btn-secondary" (click)="loadSettlement()" *ngIf="game.status === 'ending' || game.status === 'settled'">
                  <i class="bi bi-calculator me-2"></i>
                  View Settlement
                </button>
                <button class="btn btn-danger" (click)="startSettlement()" *ngIf="game.status === 'active' || game.status === 'ending'">
                  <i [class]="game?.settlement_phase ? 'bi bi-folder-open me-2' : 'bi bi-stop-circle me-2'"></i>
                  {{ game?.settlement_phase ? 'Continue Settlement' : 'Start Settlement' }}
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
                      <!-- Show Resolve button for cashouts, Approve for buyins -->
                      <button *ngIf="tx.type === 'cashout'" class="btn btn-primary btn-sm" (click)="openResolveModal(tx)">
                        <i class="bi bi-calculator me-1"></i>
                        Resolve
                      </button>
                      <button *ngIf="tx.type !== 'cashout'" class="btn btn-success btn-sm" (click)="approveTransaction(tx.id)">
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
                <input type="number" class="form-control" formControlName="amount" placeholder="Enter chip count (0 if lost all)" min="0">
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

    <!-- Resolve Cashout Modal -->
    <div class="modal fade" [class.show]="showResolveModal" [style.display]="showResolveModal ? 'block' : 'none'" tabindex="-1" *ngIf="showResolveModal">
      <div class="modal-dialog modal-dialog-centered modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="bi bi-calculator me-2"></i>
              Resolve Cashout - {{ resolveData?.playerName }}
            </h5>
            <button type="button" class="btn-close" (click)="closeResolveModal()"></button>
          </div>
          <div class="modal-body" *ngIf="resolveData">
            <!-- Information Section (Read-only) -->
            <div class="card mb-3">
              <div class="card-header bg-light">
                <strong>Cashout Information</strong>
              </div>
              <div class="card-body">
                <div class="row mb-2">
                  <div class="col-6">
                    <small class="text-muted">Credits owed by player:</small>
                    <div class="fw-bold">{{ resolveData.creditsOwed }} chips</div>
                  </div>
                  <div class="col-6">
                    <small class="text-muted">Cash player paid in:</small>
                    <div class="fw-bold">${{ resolveData.cashPaidIn }}</div>
                  </div>
                </div>
                <div class="row mb-2">
                  <div class="col-6">
                    <small class="text-muted">Chips being cashed out:</small>
                    <div class="fw-bold">{{ resolveData.cashoutAmount }} chips</div>
                  </div>
                  <div class="col-6">
                    <small class="text-muted">Credits to repay:</small>
                    <div class="fw-bold">{{ resolveData.creditsToRepay }} chips</div>
                  </div>
                </div>
                <div class="row mb-2">
                  <div class="col-6">
                    <small class="text-muted">Amount to allocate:</small>
                    <div class="fw-bold text-primary">{{ resolveData.amountToAllocate }} chips</div>
                  </div>
                  <div class="col-6">
                    <small class="text-muted">Available cash in bank:</small>
                    <div class="fw-bold">${{ resolveData.bankCashBalance }}</div>
                  </div>
                </div>
                <div class="row">
                  <div class="col-12">
                    <small class="text-muted">Unclaimed cash available:</small>
                    <div class="fw-bold text-info">${{ resolveData.unclaimedCash }}</div>
                    <small class="text-muted d-block">Cash that can be distributed (bank surplus)</small>
                  </div>
                </div>
              </div>
            </div>

            <!-- Input Section -->
            <form [formGroup]="resolveForm">
              <div class="card mb-3">
                <div class="card-header bg-light">
                  <strong>Allocation</strong>
                </div>
                <div class="card-body">
                  <div class="mb-3">
                    <label for="cashPaid" class="form-label">Cash to pay out</label>
                    <input
                      type="number"
                      class="form-control"
                      id="cashPaid"
                      formControlName="cashPaid"
                      min="0"
                      placeholder="Enter cash amount">
                    <small class="text-muted">Default: ${{ resolveData.defaultCash }}</small>
                  </div>
                  <div class="mb-3">
                    <label for="creditGiven" class="form-label">Credit to give (new debt)</label>
                    <input
                      type="number"
                      class="form-control"
                      id="creditGiven"
                      formControlName="creditGiven"
                      min="0"
                      placeholder="Enter credit amount">
                    <small class="text-muted">Default: {{ resolveData.defaultCredit }} chips</small>
                  </div>
                  
                  <!-- Validation Message -->
                  <div class="alert" 
                       [ngClass]="{
                         'alert-success': isResolveValid(),
                         'alert-danger': !isResolveValid() && (resolveForm.value.cashPaid !== null && resolveForm.value.creditGiven !== null)
                       }">
                    {{ getResolveValidationMessage() }}
                  </div>
                </div>
              </div>

              <div class="d-flex justify-content-end gap-2">
                <button type="button" class="btn btn-secondary" (click)="closeResolveModal()">Cancel</button>
                <button type="button" class="btn btn-primary" (click)="submitResolve()" [disabled]="!isResolveValid() || isLoading">
                  <i class="bi bi-check-circle me-1"></i>
                  Resolve Cashout
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade" [class.show]="showResolveModal" *ngIf="showResolveModal" (click)="closeResolveModal()"></div>

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
                        <th>Credits Owed</th>
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
                        <td class="text-danger">{{ player.credits_owed }}</td>
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

            <!-- Unpaid Credits Information -->
            <div class="card mb-3" *ngIf="gameReport.unpaid_credits && gameReport.unpaid_credits.length > 0">
              <div class="card-header bg-warning">
                <h6 class="mb-0">Unpaid Credits</h6>
              </div>
              <div class="card-body">
                <div class="table-responsive">
                  <table class="table table-sm table-striped">
                    <thead>
                      <tr>
                        <th>Player</th>
                        <th>Amount</th>
                        <th>Claimed</th>
                        <th>Available</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr *ngFor="let credit of gameReport.unpaid_credits">
                        <td>{{ credit.debtor_name }}</td>
                        <td>{{ credit.amount }}</td>
                        <td>{{ credit.amount_claimed }}</td>
                        <td>{{ credit.amount_available }}</td>
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
      <div class="modal-dialog modal-dialog-centered modal-xl">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="bi bi-calculator me-2"></i>
              Settlement - {{ game?.code }}
              <span class="badge bg-info ms-2" *ngIf="settlementStatus">
                Phase: {{ settlementStatus.phase || 'Not Started' }}
              </span>
            </h5>
            <button type="button" class="btn-close" (click)="showSettlement = false"></button>
          </div>
          <div class="modal-body" style="max-height: 70vh; overflow-y: auto;">

            <!-- Phase 1: Credit Settlement -->
            <div *ngIf="settlementStatus && settlementStatus.phase === 'credit_settlement'">
              <div class="alert alert-info">
                <i class="bi bi-info-circle me-2"></i>
                <strong>Phase 1: Credit Settlement</strong><br>
                Players with unpaid credits should repay them now using their chips.
              </div>

              <div class="card mb-3" *ngIf="settlementStatus.players_with_credits && settlementStatus.players_with_credits.length > 0">
                <div class="card-header bg-warning">
                  <h6 class="mb-0">Players with Credits to Repay</h6>
                </div>
                <div class="card-body">
                  <div class="table-responsive">
                    <table class="table table-sm table-striped">
                      <thead>
                        <tr>
                          <th>Player</th>
                          <th>Credits Owed</th>
                          <th>Credits Repaid</th>
                          <th>Remaining</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr *ngFor="let player of settlementStatus.players_with_credits">
                          <td>{{ player.name }}</td>
                          <td>{{ player.credits_owed }}</td>
                          <td class="text-success">{{ player.credits_repaid }}</td>
                          <td class="text-warning">{{ player.remaining_credits }}</td>
                          <td>
                            <div class="input-group input-group-sm" style="max-width: 200px;">
                              <input type="number" class="form-control"
                                     [id]="'repay-' + player.user_id"
                                     placeholder="Chips" min="0"
                                     [max]="player.remaining_credits">
                              <button class="btn btn-primary btn-sm"
                                      (click)="repayCredit(player.user_id, getRepayAmount(player.user_id))">
                                Repay
                              </button>
                            </div>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              <div class="text-center mt-3">
                <button class="btn btn-success" (click)="completeCreditSettlement()" *ngIf="isHost">
                  <i class="bi bi-arrow-right-circle me-1"></i>
                  Complete Credit Settlement & Move to Phase 2
                </button>
              </div>
            </div>

            <!-- Phase 2: Final Cashout -->
            <div *ngIf="settlementStatus && settlementStatus.phase === 'final_cashout'">
              <div class="alert alert-info">
                <i class="bi bi-info-circle me-2"></i>
                <strong>Phase 2: Final Cashout</strong><br>
                Players can now cash out. Choose how much cash to receive and claim unpaid credits.
              </div>

              <div class="row mb-3">
                <div class="col-md-6">
                  <div class="card">
                    <div class="card-header bg-success text-white">
                      <h6 class="mb-0">Available Cash</h6>
                    </div>
                    <div class="card-body text-center">
                      <h3 class="text-success">{{ settlementStatus.available_cash || 0 }}</h3>
                    </div>
                  </div>
                </div>
                <div class="col-md-6">
                  <div class="card">
                    <div class="card-header bg-warning text-white">
                      <h6 class="mb-0">Unpaid Credits Available</h6>
                    </div>
                    <div class="card-body">
                      <div class="table-responsive" *ngIf="settlementStatus.unpaid_credits && settlementStatus.unpaid_credits.length > 0">
                        <table class="table table-sm mb-0">
                          <thead>
                            <tr>
                              <th>Player</th>
                              <th>Available</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr *ngFor="let credit of settlementStatus.unpaid_credits">
                              <td>{{ credit.debtor_name }}</td>
                              <td>{{ credit.amount_available }}</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                      <p class="text-center mb-0" *ngIf="!settlementStatus.unpaid_credits || settlementStatus.unpaid_credits.length === 0">
                        No unpaid credits
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Final Cashout Form -->
              <div class="card mb-3">
                <div class="card-header bg-primary text-white">
                  <h6 class="mb-0">Process Final Cashout</h6>
                </div>
                <div class="card-body">
                  <form [formGroup]="finalCashoutForm" (ngSubmit)="processFinalCashout()">
                    <div class="row">
                      <div class="col-md-4">
                        <label class="form-label">Select Player</label>
                        <select class="form-control" formControlName="userId">
                          <option value="">Choose player...</option>
                          <option *ngFor="let player of getActivePlayers()" [value]="player.user_id">
                            {{ player.name }}
                          </option>
                        </select>
                      </div>
                      <div class="col-md-2">
                        <label class="form-label">Chips</label>
                        <input type="number" class="form-control" formControlName="chips" placeholder="0" min="0">
                      </div>
                      <div class="col-md-2">
                        <label class="form-label">Cash Requested</label>
                        <input type="number" class="form-control" formControlName="cashRequested" placeholder="0" min="0">
                      </div>
                      <div class="col-md-4">
                        <label class="form-label">Claim Unpaid Credits</label>
                        <div *ngFor="let credit of settlementStatus.unpaid_credits; let i = index" class="mb-1">
                          <div class="input-group input-group-sm">
                            <span class="input-group-text">{{ credit.debtor_name }}</span>
                            <input type="number" class="form-control"
                                   [id]="'claim-' + credit.debtor_user_id"
                                   placeholder="Amount" min="0"
                                   [max]="credit.amount_available">
                          </div>
                        </div>
                      </div>
                    </div>
                    <div class="text-center mt-3">
                      <button type="submit" class="btn btn-success" [disabled]="finalCashoutForm.invalid || isLoading">
                        <i class="bi bi-check-circle me-1"></i>
                        Process Cashout
                      </button>
                    </div>
                  </form>
                </div>
              </div>

              <div class="text-center mt-3">
                <button class="btn btn-danger" (click)="completeSettlement()" *ngIf="isHost">
                  <i class="bi bi-flag-fill me-1"></i>
                  Complete Settlement & End Game
                </button>
              </div>
            </div>

            <!-- Settlement Summary View -->
            <div *ngIf="settlementSummary">
              <div class="alert alert-success">
                <i class="bi bi-check-circle me-2"></i>
                <strong>Settlement Complete</strong><br>
                Review the final settlement summary below.
              </div>

              <div class="card mb-3">
                <div class="card-header bg-info text-white">
                  <h6 class="mb-0">All Players Summary</h6>
                </div>
                <div class="card-body">
                  <div class="table-responsive">
                    <table class="table table-sm table-striped">
                      <thead>
                        <tr>
                          <th>Player</th>
                          <th>Cash Buy-ins</th>
                          <th>Credit Buy-ins</th>
                          <th>Total Buy-ins</th>
                          <th>Cashouts</th>
                          <th>Net</th>
                          <th>Unpaid Credits</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr *ngFor="let summary of settlementSummary.summaries">
                          <td>{{ summary.name }}</td>
                          <td>{{ summary.totals.cash_buyins }}</td>
                          <td>{{ summary.totals.credit_buyins }}</td>
                          <td>{{ summary.totals.total_buyins }}</td>
                          <td>{{ summary.totals.cashouts }}</td>
                          <td [class]="summary.totals.net >= 0 ? 'text-success' : 'text-danger'">
                            {{ summary.totals.net > 0 ? '+' : '' }}{{ summary.totals.net }}
                          </td>
                          <td class="text-warning">{{ summary.unpaid_credit_owed }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>

            <!-- No Settlement Started (Host only) -->
            <div *ngIf="(!settlementStatus || !settlementStatus.phase) && !settlementSummary && isHost">
              <div class="alert alert-warning">
                <i class="bi bi-exclamation-triangle me-2"></i>
                Settlement has not been started yet. Click "Start Settlement" to begin the settlement process.
              </div>
            </div>

            <!-- Player View: Show individual summary when settlement exists -->
            <div *ngIf="(!settlementStatus || !settlementStatus.phase) && !settlementSummary && !isHost && playerSettlementSummary">
              <div class="alert alert-info">
                <i class="bi bi-info-circle me-2"></i>
                <strong>Your Settlement Summary</strong>
              </div>

              <div class="card mb-3">
                <div class="card-body">
                  <h6 class="text-muted mb-3">Your Totals</h6>
                  <div class="row g-2 mb-3">
                    <div class="col-6">
                      <small class="text-muted">Cash Buy-ins:</small>
                      <div class="fw-bold text-success">{{ playerSettlementSummary.totals.cash_buyins }}</div>
                    </div>
                    <div class="col-6">
                      <small class="text-muted">Credit Buy-ins:</small>
                      <div class="fw-bold text-warning">{{ playerSettlementSummary.totals.credit_buyins }}</div>
                    </div>
                    <div class="col-6">
                      <small class="text-muted">Cashouts:</small>
                      <div class="fw-bold">{{ playerSettlementSummary.totals.cashouts }}</div>
                    </div>
                    <div class="col-6">
                      <small class="text-muted">Net:</small>
                      <div class="fw-bold" [class.text-success]="playerSettlementSummary.totals.net >= 0" [class.text-danger]="playerSettlementSummary.totals.net < 0">
                        {{ playerSettlementSummary.totals.net > 0 ? '+' : '' }}{{ playerSettlementSummary.totals.net }}
                      </div>
                    </div>
                  </div>

                  <div *ngIf="playerSettlementSummary.owes_to_me && playerSettlementSummary.owes_to_me.length > 0">
                    <h6 class="text-muted mb-2">Who Owes You</h6>
                    <div class="list-group list-group-flush mb-3">
                      <div class="list-group-item px-0 py-2 d-flex justify-content-between" *ngFor="let debt of playerSettlementSummary.owes_to_me">
                        <span>{{ debt.debtor_name }}</span>
                        <span class="badge bg-warning">{{ debt.amount }}</span>
                      </div>
                    </div>
                  </div>

                  <div *ngIf="playerSettlementSummary.i_owe && playerSettlementSummary.i_owe.length > 0">
                    <h6 class="text-muted mb-2">What You Owe</h6>
                    <div class="list-group list-group-flush">
                      <div class="list-group-item px-0 py-2 d-flex justify-content-between" *ngFor="let owed of playerSettlementSummary.i_owe">
                        <span class="small">{{ owed.note }}</span>
                        <span class="badge bg-danger">{{ owed.amount }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" (click)="showSettlement = false">Close</button>
            <button type="button" class="btn btn-info" (click)="viewSettlementSummary()" *ngIf="isHost">
              <i class="bi bi-file-text me-1"></i>
              View Full Summary
            </button>
            <button type="button" class="btn btn-outline-info" (click)="viewMySettlementSummary()" *ngIf="isHost && !settlementSummary">
              <i class="bi bi-person-circle me-1"></i>
              View My Summary
            </button>
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
  bankStatus: BankStatus | null = null;
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
  showResolveModal = false;
  qrCodeDataUrl = '';
  gameJoinUrl = '';
  gameReport: any = null;
  settlementData: any = null;
  settlementStatus: SettlementStatus | null = null;
  settlementSummary: AllSettlementSummaries | null = null;
  playerSettlementSummary: SettlementSummary | null = null;
  
  // Resolve modal data
  resolveTransaction: Transaction | null = null;
  resolveData: any = null;

  // Forms
  buyinForm: FormGroup;
  cashoutForm: FormGroup;
  hostBuyinForm: FormGroup;
  hostCashoutForm: FormGroup;
  finalCashoutForm: FormGroup;
  resolveForm: FormGroup;

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
      amount: ['', [Validators.required, Validators.min(0)]]
    });

    this.hostBuyinForm = this.formBuilder.group({
      player: ['', [Validators.required]],
      amount: ['', [Validators.required, Validators.min(1)]],
      type: ['cash', [Validators.required]]
    });

    this.hostCashoutForm = this.formBuilder.group({
      player: ['', [Validators.required]],
      amount: ['', [Validators.required, Validators.min(0)]]
    });

    this.finalCashoutForm = this.formBuilder.group({
      userId: ['', [Validators.required]],
      chips: ['', [Validators.required, Validators.min(0)]],
      cashRequested: ['', [Validators.required, Validators.min(0)]]
    });

    this.resolveForm = this.formBuilder.group({
      cashPaid: ['', [Validators.required, Validators.min(0)]],
      creditGiven: ['', [Validators.required, Validators.min(0)]]
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

  loadBankStatus(): void {
    if (this.game) {
      this.apiService.getBank(this.game.id).subscribe({
        next: (status) => {
          this.bankStatus = status;
        },
        error: (error) => {
          console.error('Failed to load bank status:', error);
        }
      });
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

    // Load bank status
    this.loadBankStatus();

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
                  credits_owed: 0,
                  transactions: []
                };
              }
            });

            // Load player settlement summary if game is ending or settled
            if (this.game && (this.game.status === 'ending' || this.game.status === 'settled')) {
              this.apiService.getPlayerSettlementSummary(gameId, this.currentPlayerUserId).subscribe({
                next: (summary) => {
                  this.playerSettlementSummary = summary;
                  console.log('Player settlement summary loaded:', summary);
                },
                error: (error) => {
                  console.error('Failed to load player settlement summary:', error);
                }
              });
            }
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
        this.loadBankStatus();
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
        this.loadBankStatus();
        this.refreshData();
      },
      error: (error) => {
        this.showError(error.error?.message || 'Failed to reject transaction');
      }
    });
  }

  openResolveModal(transaction: Transaction): void {
    if (!this.game) {
      return;
    }

    this.resolveTransaction = transaction;
    this.isLoading = true;

    // Load resolve data (player info, bank info, etc.)
    const gameId = this.game.id;
    const userId = transaction.user_id;
    const cashoutAmount = transaction.amount;

    // Get player summary and bank status
    this.apiService.getPlayerSummary(gameId, userId).subscribe({
      next: (playerSummary) => {
        const player = this.players.find(p => p.user_id === userId);
        const creditsOwed = playerSummary.credits_owed;
        
        // Get player's cash buyins
        this.apiService.getPlayerBuyinSummary(gameId, userId).subscribe({
          next: (buyinSummary) => {
            const creditsToRepay = Math.min(cashoutAmount, creditsOwed);
            const amountToAllocate = Math.max(0, cashoutAmount - creditsToRepay);
            
            // Calculate defaults
            const defaultCash = Math.min(buyinSummary.cash_buyins, amountToAllocate);
            const defaultCredit = amountToAllocate - defaultCash;
            
            // Calculate unclaimed cash (bank surplus)
            const unclaimedCash = this.bankStatus ? 
              this.bankStatus.cash_balance - buyinSummary.cash_buyins : 0;
            
            this.resolveData = {
              playerName: player?.name || 'Player',
              creditsOwed: creditsOwed,
              cashPaidIn: buyinSummary.cash_buyins,
              cashoutAmount: cashoutAmount,
              creditsToRepay: creditsToRepay,
              amountToAllocate: amountToAllocate,
              unclaimedCash: Math.max(0, unclaimedCash),
              bankCashBalance: this.bankStatus?.cash_balance || 0,
              defaultCash: defaultCash,
              defaultCredit: defaultCredit
            };
            
            // Set form defaults
            this.resolveForm.patchValue({
              cashPaid: defaultCash,
              creditGiven: defaultCredit
            });
            
            this.isLoading = false;
            this.showResolveModal = true;
          },
          error: (error) => {
            this.isLoading = false;
            this.showError('Failed to load player buyin summary');
          }
        });
      },
      error: (error) => {
        this.isLoading = false;
        this.showError('Failed to load player summary');
      }
    });
  }

  closeResolveModal(): void {
    this.showResolveModal = false;
    this.resolveTransaction = null;
    this.resolveData = null;
    this.resolveForm.reset();
  }

  getResolveValidationMessage(): string {
    if (!this.resolveData || !this.resolveForm.value.cashPaid || !this.resolveForm.value.creditGiven) {
      return '';
    }

    const cashPaid = parseInt(this.resolveForm.value.cashPaid, 10);
    const creditGiven = parseInt(this.resolveForm.value.creditGiven, 10);
    const sum = cashPaid + creditGiven;
    const expected = this.resolveData.amountToAllocate;

    if (sum !== expected) {
      return `❌ Must equal ${expected} (currently ${sum})`;
    }

    if (cashPaid > this.resolveData.bankCashBalance) {
      return `❌ Cash exceeds bank balance (${this.resolveData.bankCashBalance})`;
    }

    return `✓ Valid allocation`;
  }

  isResolveValid(): boolean {
    if (!this.resolveData || !this.resolveForm.valid) {
      return false;
    }

    const cashPaid = parseInt(this.resolveForm.value.cashPaid, 10);
    const creditGiven = parseInt(this.resolveForm.value.creditGiven, 10);
    const sum = cashPaid + creditGiven;

    return sum === this.resolveData.amountToAllocate && cashPaid <= this.resolveData.bankCashBalance;
  }

  submitResolve(): void {
    if (!this.resolveTransaction || !this.resolveForm.valid || !this.isResolveValid()) {
      return;
    }

    const cashPaid = parseInt(this.resolveForm.value.cashPaid, 10);
    const creditGiven = parseInt(this.resolveForm.value.creditGiven, 10);

    this.isLoading = true;
    this.apiService.resolveTransaction(this.resolveTransaction.id, cashPaid, creditGiven).subscribe({
      next: (response) => {
        this.isLoading = false;
        this.closeResolveModal();
        this.showSuccess('Cashout resolved successfully');
        this.loadBankStatus();
        this.refreshData();
      },
      error: (error) => {
        this.isLoading = false;
        this.showError(error.error?.error || 'Failed to resolve cashout');
      }
    });
  }

  startSettlement(): void {
    if (!this.game) {
      return;
    }

    const gameId = this.game.id;

    // First check if settlement is already started
    this.apiService.getSettlementStatus(gameId).subscribe({
      next: (status) => {
        // Settlement already exists - just open the modal
        if (status.phase) {
          this.settlementStatus = status;
          this.showSettlement = true;
        } else {
          // No settlement yet - confirm and start it
          this.confirmAndStartNewSettlement(gameId);
        }
      },
      error: (error) => {
        // No settlement exists yet - confirm and start it
        this.confirmAndStartNewSettlement(gameId);
      }
    });
  }

  private confirmAndStartNewSettlement(gameId: string): void {
    if (confirm('Are you sure you want to start settlement? This will begin the settlement process.')) {
        this.apiService.startSettlement(gameId).subscribe({
          next: (response) => {
            this.settlementStatus = response;
            this.showSuccess('Settlement started successfully');
            this.showSettlement = true;
            this.refreshData();
          },
          error: (error) => {
            this.showError(error.error?.message || 'Failed to start settlement');
          }
        });
    }
  }

  repayCredit(userId: number, chips: number): void {
    if (!this.game || chips <= 0) {
      this.showError('Invalid repayment amount');
      return;
    }

    const gameId = this.game.id;

    this.isLoading = true;
    this.apiService.repayCredit(gameId, userId, chips).subscribe({
      next: (response) => {
        this.isLoading = false;
        this.showSuccess('Credit repayment processed successfully');
        this.loadSettlementStatus();
      },
      error: (error) => {
        this.isLoading = false;
        this.showError(error.error?.message || 'Failed to process credit repayment');
      }
    });
  }

  completeCreditSettlement(): void {
    if (!this.game) {
      return;
    }

    const gameId = this.game.id;

    if (confirm('Complete credit settlement and move to final cashout phase?')) {
        this.apiService.completeCreditSettlement(gameId).subscribe({
          next: (response) => {
            this.settlementStatus = response;
            this.showSuccess('Credit settlement complete. Moving to final cashout phase.');
            this.loadSettlementStatus();
          },
          error: (error) => {
            this.showError(error.error?.message || 'Failed to complete credit settlement');
          }
        });
    }
  }

  processFinalCashout(): void {
    if (this.finalCashoutForm.invalid || !this.game) {
      return;
    }

    const gameId = this.game.id;
    const userId = parseInt(this.finalCashoutForm.value.userId, 10);
    const chips = parseInt(this.finalCashoutForm.value.chips, 10);
    const cashRequested = parseInt(this.finalCashoutForm.value.cashRequested, 10);

    // Collect unpaid credits claimed
    const unpaidCreditsClaimed: Array<{debtor_user_id: number; amount: number}> = [];
    if (this.settlementStatus?.unpaid_credits) {
      this.settlementStatus.unpaid_credits.forEach(credit => {
        const inputElement = document.getElementById(`claim-${credit.debtor_user_id}`) as HTMLInputElement;
        if (inputElement && inputElement.value) {
          const amount = parseInt(inputElement.value, 10);
          if (amount > 0) {
            unpaidCreditsClaimed.push({
              debtor_user_id: credit.debtor_user_id,
              amount: amount
            });
          }
        }
      });
    }

    this.isLoading = true;
    this.apiService.finalCashout(gameId, userId, chips, cashRequested, unpaidCreditsClaimed).subscribe({
      next: (response) => {
        this.isLoading = false;
        this.finalCashoutForm.reset();
        this.showSuccess('Final cashout processed successfully');
        this.loadSettlementStatus();
      },
      error: (error) => {
        this.isLoading = false;
        this.showError(error.error?.message || 'Failed to process final cashout');
      }
    });
  }

  completeSettlement(): void {
    if (!this.game) {
      return;
    }

    const gameId = this.game.id;

    // First check if settlement can be completed
    this.apiService.checkSettlementComplete(gameId).subscribe({
      next: (checkResult) => {
        if (checkResult.can_complete) {
          if (confirm('Complete settlement and end the game? This cannot be undone.')) {
            this.apiService.completeSettlement(gameId).subscribe({
              next: (response) => {
                this.showSuccess('Settlement completed successfully. Game ended.');
                this.showSettlement = false;
                this.refreshData();
              },
              error: (error) => {
                this.showError(error.error?.message || 'Failed to complete settlement');
              }
            });
          }
        } else {
          this.showError(checkResult.message || 'Cannot complete settlement yet');
        }
      },
      error: (error) => {
        this.showError(error.error?.message || 'Failed to check settlement status');
      }
    });
  }

  viewSettlementSummary(): void {
    if (!this.game) {
      return;
    }

    const gameId = this.game.id;

    this.apiService.getAllSettlementSummaries(gameId).subscribe({
        next: (summary) => {
          this.settlementSummary = summary;
          this.settlementStatus = null; // Switch to summary view
        },
        error: (error) => {
          this.showError('Failed to load settlement summary');
        }
      });
  }

  viewMySettlementSummary(): void {
    // Host viewing their own settlement summary
    // This will trigger the playerSettlementSummary to be shown in the modal
    this.settlementStatus = null;
    this.settlementSummary = null;
    // The playerSettlementSummary should already be loaded from sidebar
    // If not, it will show in the sidebar already
    this.showSettlement = false;
    // Just point them to look at the sidebar
    this.showSuccess('Your settlement summary is shown in the left sidebar under "Your Settlement Summary"');
  }

  getRepayAmount(userId: number): number {
    const inputElement = document.getElementById(`repay-${userId}`) as HTMLInputElement;
    if (inputElement && inputElement.value) {
      return parseInt(inputElement.value, 10);
    }
    return 0;
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

  isCurrentPlayerInactive(): boolean {
    if (!this.currentPlayerUserId) {
      return false;
    }
    const currentPlayer = this.players.find(p => p.user_id === this.currentPlayerUserId);
    return currentPlayer ? currentPlayer.cashed_out : false;
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

          // Show detailed cashout breakdown
          const message = response.message || 'Cashout processed successfully';
          const breakdown = response.cashout_breakdown;

          if (breakdown) {
            // Format detailed message
            let detailedMsg = `Cashout Complete!\n\n`;
            detailedMsg += `Total chips: ${breakdown.total_chips}\n`;

            if (breakdown.credit_repaid > 0) {
              detailedMsg += `Credit repaid: ${breakdown.credit_repaid} chips\n`;
            }

            if (breakdown.remaining_credit > 0) {
              detailedMsg += `⚠ Remaining credit owed: $${breakdown.remaining_credit}\n`;
            }

            if (breakdown.cash_received > 0) {
              detailedMsg += `Cash received: $${breakdown.cash_received}\n`;
            }

            if (breakdown.unpaid_credits_created && breakdown.unpaid_credits_created.length > 0) {
              detailedMsg += `\nUnpaid credits created:\n`;
              breakdown.unpaid_credits_created.forEach((credit: any) => {
                detailedMsg += `  • ${credit.debtor_name} owes $${credit.amount}\n`;
              });
            }

            alert(detailedMsg);
          } else {
            this.showSuccess(message);
          }

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
      // If settlement is completed (phase = 'completed'), show summary directly
      if (this.game.settlement_phase === 'completed') {
        this.viewSettlementSummary();
      }
      // If game is settled but no settlement phase (old games), show summary directly
      else if (this.game.status === 'settled' && !this.game.settlement_phase) {
        this.viewSettlementSummary();
      } else {
        this.loadSettlementStatus();
      }
      this.showSettlement = true;
    }
  }

  loadSettlementStatus(): void {
    if (this.game) {
      this.apiService.getSettlementStatus(this.game.id).subscribe({
        next: (status) => {
          this.settlementStatus = status;
          // Clear summary when loading status
          this.settlementSummary = null;

          // If settlement phase is 'completed', show summary
          if (this.game?.settlement_phase === 'completed') {
            this.viewSettlementSummary();
          }
          // If game is settled but no phase in status, show summary instead
          else if (this.game?.status === 'settled' && !status.phase) {
            this.viewSettlementSummary();
          }
        },
        error: (error) => {
          // If settlement completed or game settled, show summary
          if (this.game?.settlement_phase === 'completed' || this.game?.status === 'settled') {
            console.log('Settlement completed or game settled, showing summary');
            this.viewSettlementSummary();
          } else {
            console.log('No settlement status available:', error);
            this.settlementStatus = null;
          }
        }
      });
    }
  }

  getActivePlayers(): Player[] {
    return this.players.filter(p => p.active && !p.quit);
  }

  formatTransactionDate(dateString: string | Date): string {
    if (!dateString) return '';

    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    // If within last minute
    if (diffMins < 1) {
      return 'Just now';
    }
    // If within last hour
    else if (diffMins < 60) {
      return `${diffMins}m ago`;
    }
    // If within last 24 hours
    else if (diffHours < 24) {
      return `${diffHours}h ago`;
    }
    // If within last week
    else if (diffDays < 7) {
      return `${diffDays}d ago`;
    }
    // Otherwise show full date and time
    else {
      return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    }
  }
}