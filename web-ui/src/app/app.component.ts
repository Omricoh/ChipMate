import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, RouterModule, Router } from '@angular/router';
import { NavbarComponent } from './components/navbar/navbar.component';
import { ApiService } from './services/api.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterModule, NavbarComponent],
  template: `
    <div class="main-container">
      <app-navbar></app-navbar>
      <main class="flex-grow-1">
        <router-outlet></router-outlet>
      </main>
    </div>
  `,
  styles: []
})
export class AppComponent implements OnInit {
  title = 'ChipMate - Poker Game Manager';

  constructor(
    private apiService: ApiService,
    private router: Router
  ) {}

  ngOnInit(): void {
    const currentUser = this.apiService.getCurrentUser();
    
    // Only auto-redirect if we're not already on the game page or login page
    const currentRoute = this.router.url;
    const isOnGamePage = currentRoute.startsWith('/game/');
    const isOnLoginPage = currentRoute.startsWith('/login');
    
    if (currentUser && currentUser.current_game_id && !isOnGamePage && !isOnLoginPage) {
      this.apiService.getGame(currentUser.current_game_id).subscribe({
        next: (game) => {
          if (game.status === 'active') {
            this.router.navigate(['/game', currentUser.current_game_id]);
          } else {
            currentUser.current_game_id = undefined;
            this.apiService.setCurrentUser(currentUser);
          }
        },
        error: () => {
          currentUser.current_game_id = undefined;
          this.apiService.setCurrentUser(currentUser);
        }
      });
    }
  }
}