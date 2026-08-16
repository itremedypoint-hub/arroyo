import { loadCore } from "./extract.mjs";
const { TRAINING_DATA } = loadCore();
process.stdout.write(JSON.stringify(TRAINING_DATA, null, 2));
