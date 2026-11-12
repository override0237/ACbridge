import { createApp } from './app.js';
import { createStore } from './store.js';

const port = process.env.PORT || 4000;
createApp(createStore()).listen(port, () => {
  console.log(`ACbridge API running on http://localhost:${port}`);
});
