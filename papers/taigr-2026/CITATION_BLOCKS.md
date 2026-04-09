# Citation Blocks for Project READMEs

Add these to the READMEs of veritas, veritasbench, and cliniclaw.

---

## For ALL THREE repos (veritas, veritasbench, cliniclaw)

### Zenodo Badge (add near top, after logo)

```markdown
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19403623.svg)](https://doi.org/10.5281/zenodo.19403623)
```

### Citation Section (add before Contributing or at bottom)

```markdown
## Citation

If you use or reference VERITAS, VeritasBench, or ClinicLaw in academic work, please cite:

> Guan, Z. (2026). *VERITAS: A Governance Runtime and Benchmark Framework for AI Agents in Regulated Environments.* Zenodo. [https://doi.org/10.5281/zenodo.19403623](https://doi.org/10.5281/zenodo.19403623)

```bibtex
@techreport{guan2026veritas,
  author    = {Ziyuan Guan},
  title     = {VERITAS: A Governance Runtime and Benchmark Framework for AI Agents in Regulated Environments},
  year      = {2026},
  doi       = {10.5281/zenodo.19403623},
  url       = {https://doi.org/10.5281/zenodo.19403623},
  publisher = {Zenodo},
  note      = {Technical report covering VERITAS runtime, VeritasBench benchmark, and ClinicLaw reference implementation. Under review at TAIGR @ ICML 2026.}
}
```

### Related Work (add to veritas and cliniclaw READMEs)

```markdown
## Related Projects

- **[VeritasBench](https://github.com/Chesterguan/veritasbench)** — Benchmark framework for AI agent governance
- **[VERITAS](https://github.com/Chesterguan/veritas)** — Governance runtime for AI agents in regulated environments
- **[ClinicLaw](https://github.com/Chesterguan/cliniclaw)** — AI-native HIS with VERITAS governance layer
- **[HAVEN](https://github.com/Chesterguan/HAVEN)** — Patient-controlled health data protocol ([DOI: 10.5281/zenodo.18701303](https://doi.org/10.5281/zenodo.18701303))
```
