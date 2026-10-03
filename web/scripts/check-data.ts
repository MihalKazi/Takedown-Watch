/** `npm run check:data`: validate ../data/v1 against the contract without building the site. */
import { dataDir, loadDataset } from "../src/schemas/dataset.ts";

try {
  const d = loadDataset();
  const published = d.coverage.groups.filter((g) => !g.suppressed).length;
  console.log(
    `ok  ${dataDir()}  schema ${d.meta.schema_version}  ${d.outlets.outlets.length} outlets, ` +
      `${published}/${d.coverage.groups.length} groups published, ${d.volume.series.length} days`,
  );
} catch (e) {
  console.error((e as Error).message);
  process.exit(1);
}
