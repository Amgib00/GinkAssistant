## 1. Build
- [x] 1.1 services/wake_status.py: describe() -> state, short label, full sentence
- [x] 1.2 ui/wake_ui.py: the chip (wakeChip), reduced-motion and narrow-screen styles; click -> Settings > Voice
- [x] 1.3 ui/main_screen.py: push the chip on changes (polled ~0.6 s, and at once when a wake turn starts and ends); download progress; Settings > Voice uses the same states
- [x] 1.4 Tests: tests/test_wake_status.py (every state, the Android permission regression), tests/test_wake_word.py (the chip follows a real wake turn)

## 2. Check on devices
- [ ] 2.1 Real-browser look of the chip (light, dark, home composer, narrow window)
- [ ] 2.2 Mac (Catalina build): green while waiting, lime on "Hey Gink", grey while answering
- [ ] 2.3 32-bit Android (TECNO BF6): turn the mic permission off -> red chip with the reason; tap opens Voice settings
