/**
 * 3D Heat Transfer Simulation (FTCS)
 * Граничные условия: 6 граней с независимыми температурами
 * Параллельная версия: OpenMP (число потоков — флаг --threads N)
 *
 * Сборка:
 *   Linux   : g++ -O2 -fopenmp -std=c++17 heat3d.cpp -o heat3d
 *   Windows : x86_64-w64-mingw32-g++ -O2 -fopenmp -std=c++17 -static heat3d.cpp -o heat3d.exe
 *   Visual Studio: C/C++ -> Язык -> Поддержка OpenMP = Да (/openmp), стандарт C++17
 * Без -fopenmp (/openmp) получается последовательная версия.
 */

#include <iostream>
#include <fstream>
#include <vector>
#include <cmath>
#include <iomanip>
#include <string>
#include <chrono>
#ifdef _WIN32
#include <direct.h>
#else
#include <sys/stat.h>
#endif
#ifdef _OPENMP
#include <omp.h>
#endif

using Grid3D = std::vector<double>;

inline int idx(int i, int j, int k, int NY, int NZ) {
    return i * NY * NZ + j * NZ + k;
}

double computeStableDt(double dx, double dy, double dz, double alpha) {
    double inv = 1.0/(dx*dx) + 1.0/(dy*dy) + 1.0/(dz*dz);
    return 0.4 / (2.0 * alpha * inv);
}

double centerTemp(const Grid3D& T, int NX, int NY, int NZ) {
    return T[idx(NX/2, NY/2, NZ/2, NY, NZ)];
}

double meanTemp(const Grid3D& T) {
    double sum = 0.0;
    const int n = (int)T.size();
    #pragma omp parallel for reduction(+:sum) schedule(static)
    for (int q = 0; q < n; ++q) sum += T[q];
    return sum / (double)T.size();
}

void saveSliceZ(const Grid3D& T, int step, int NX, int NY, int NZ,
                double dx, double dy, const std::string& dir) {
    int k = NZ / 2;
    std::ofstream f(dir + "/slice_z_step" + std::to_string(step) + ".csv");
    f << "x,y,T\n";
    for (int i = 0; i < NX; ++i)
        for (int j = 0; j < NY; ++j)
            f << std::fixed << std::setprecision(6)
              << i*dx << "," << j*dy << "," << T[idx(i,j,k,NY,NZ)] << "\n";
}

void saveSliceY(const Grid3D& T, int step, int NX, int NY, int NZ,
                double dx, double dz, const std::string& dir) {
    int j = NY / 2;
    std::ofstream f(dir + "/slice_y_step" + std::to_string(step) + ".csv");
    f << "x,z,T\n";
    for (int i = 0; i < NX; ++i)
        for (int k = 0; k < NZ; ++k)
            f << std::fixed << std::setprecision(6)
              << i*dx << "," << k*dz << "," << T[idx(i,j,k,NY,NZ)] << "\n";
}

struct Params {
    int    nx = 30, ny = 30, nz = 30;
    double lx = 1.0, ly = 1.0, lz = 1.0;
    double alpha      = 1.28e-5;
    double t_end      = 50000.0;
    double t_init     = 20.0;
    double t_xm = 100.0, t_xp = 100.0;
    double t_ym = 100.0, t_yp = 100.0;
    double t_zm = 100.0, t_zp = 100.0;
    int    save_every = 500;
    int    threads    = 0;   // 0 — по умолчанию OpenMP (все ядра)
};

Params parseArgs(int argc, char* argv[]) {
    Params p;
    for (int i = 1; i < argc - 1; ++i) {
        std::string key(argv[i]), val(argv[i+1]);
        if      (key=="--nx")         { p.nx         = std::stoi(val); ++i; }
        else if (key=="--ny")         { p.ny         = std::stoi(val); ++i; }
        else if (key=="--nz")         { p.nz         = std::stoi(val); ++i; }
        else if (key=="--alpha")      { p.alpha      = std::stod(val); ++i; }
        else if (key=="--t_end")      { p.t_end      = std::stod(val); ++i; }
        else if (key=="--t_init")     { p.t_init     = std::stod(val); ++i; }
        else if (key=="--t_xm")       { p.t_xm       = std::stod(val); ++i; }
        else if (key=="--t_xp")       { p.t_xp       = std::stod(val); ++i; }
        else if (key=="--t_ym")       { p.t_ym       = std::stod(val); ++i; }
        else if (key=="--t_yp")       { p.t_yp       = std::stod(val); ++i; }
        else if (key=="--t_zm")       { p.t_zm       = std::stod(val); ++i; }
        else if (key=="--t_zp")       { p.t_zp       = std::stod(val); ++i; }
        else if (key=="--save_every") { p.save_every = std::stoi(val); ++i; }
        else if (key=="--threads")    { p.threads    = std::stoi(val); ++i; }
    }
    return p;
}

int main(int argc, char* argv[]) {
    using namespace std::chrono;
    Params p = parseArgs(argc, argv);

    if (p.nx < 3) p.nx = 3;
    if (p.ny < 3) p.ny = 3;
    if (p.nz < 3) p.nz = 3;
    if (p.alpha <= 0) p.alpha = 1.28e-5;
    if (p.t_end <= 0) p.t_end = 1000.0;
    if (p.save_every < 1) p.save_every = 1;

    const double dx = p.lx / (p.nx - 1);
    const double dy = p.ly / (p.ny - 1);
    const double dz = p.lz / (p.nz - 1);
    const double dt = computeStableDt(dx, dy, dz, p.alpha);
    const int NSTEPS = static_cast<int>(p.t_end / dt) + 1;

    int nThreads = 1;
#ifdef _OPENMP
    if (p.threads > 0) omp_set_num_threads(p.threads);
    nThreads = omp_get_max_threads();
#endif

    std::cout << "========================================\n";
    std::cout << "  3D Heat Transfer Simulation (FTCS)\n";
    std::cout << "========================================\n";
    std::cout << "  Grid      : " << p.nx << " x " << p.ny << " x " << p.nz << "\n";
    std::cout << "  alpha     : " << p.alpha << " m^2/s\n";
    std::cout << "  dt        : " << dt << " s\n";
    std::cout << "  T_end     : " << p.t_end << " s\n";
    std::cout << "  T_init    : " << p.t_init << " C\n";
    std::cout << "  X- / X+   : " << p.t_xm << " / " << p.t_xp << " C\n";
    std::cout << "  Y- / Y+   : " << p.t_ym << " / " << p.t_yp << " C\n";
    std::cout << "  Z- / Z+   : " << p.t_zm << " / " << p.t_zp << " C\n";
    std::cout << "  Steps     : " << NSTEPS << "\n";
    std::cout << "  Threads   : " << nThreads << "\n";
    std::cout << "========================================\n\n";

#ifdef _WIN32
    _mkdir("output");
#else
    mkdir("output", 0755);
#endif
    std::string outDir = "output";

    Grid3D T(p.nx * p.ny * p.nz, p.t_init);
    Grid3D T_new(p.nx * p.ny * p.nz, 0.0);

    auto applyBC = [&](Grid3D& g) {
        #pragma omp parallel for schedule(static)
        for (int j = 0; j < p.ny; ++j)
            for (int k = 0; k < p.nz; ++k) {
                g[idx(0,      j, k, p.ny, p.nz)] = p.t_xm;
                g[idx(p.nx-1, j, k, p.ny, p.nz)] = p.t_xp;
            }
        #pragma omp parallel for schedule(static)
        for (int i = 0; i < p.nx; ++i)
            for (int k = 0; k < p.nz; ++k) {
                g[idx(i, 0,      k, p.ny, p.nz)] = p.t_ym;
                g[idx(i, p.ny-1, k, p.ny, p.nz)] = p.t_yp;
            }
        #pragma omp parallel for schedule(static)
        for (int i = 0; i < p.nx; ++i)
            for (int j = 0; j < p.ny; ++j) {
                g[idx(i, j, 0,       p.ny, p.nz)] = p.t_zm;
                g[idx(i, j, p.nz-1,  p.ny, p.nz)] = p.t_zp;
            }
    };

    applyBC(T);

    std::ofstream histFile(outDir + "/history.csv");
    histFile << "step,time,T_center,T_mean\n";

    const double rx = p.alpha * dt / (dx * dx);
    const double ry = p.alpha * dt / (dy * dy);
    const double rz = p.alpha * dt / (dz * dz);

    std::cout << "  Stability sum: " << 2*(rx+ry+rz) << " (must be < 1)\n\n";

    const int NIJ = (p.nx - 2) * (p.ny - 2);

    auto t0 = high_resolution_clock::now();
    double time = 0.0;

    for (int step = 0; step <= NSTEPS; ++step) {
        if (step % p.save_every == 0) {
            double Tc    = centerTemp(T, p.nx, p.ny, p.nz);
            double Tmean = meanTemp(T);
            histFile << step << "," << std::fixed << std::setprecision(4)
                     << time << "," << Tc << "," << Tmean << "\n";
            histFile.flush();
            saveSliceZ(T, step, p.nx, p.ny, p.nz, dx, dy, outDir);
            saveSliceY(T, step, p.nx, p.ny, p.nz, dx, dz, outDir);
            std::cout << "  step=" << std::setw(6) << step
                      << "  t=" << std::setw(10) << std::fixed << std::setprecision(2) << time << " s"
                      << "  T_center=" << std::setw(8) << std::setprecision(3) << Tc << " C"
                      << "  T_mean=" << std::setw(8) << std::setprecision(3) << Tmean << " C\n";
            std::cout.flush();
        }
        if (step == NSTEPS) break;

        // Циклы по i и j слиты в один (аналог collapse(2), но совместимо
        // с OpenMP 2.0 в Visual Studio): (nx-2)*(ny-2) независимых столбцов по k
        // делятся между потоками поровну. Каждая точка T_new пишется ровно
        // одним потоком, T только читается — гонок данных нет.
        #pragma omp parallel for schedule(static)
        for (int ij = 0; ij < NIJ; ++ij) {
            const int i = 1 + ij / (p.ny - 2);
            const int j = 1 + ij % (p.ny - 2);
            for (int k = 1; k < p.nz-1; ++k) {
                double Tijk = T[idx(i,  j,  k,  p.ny, p.nz)];
                double d2x  = T[idx(i+1,j,  k,  p.ny, p.nz)] - 2*Tijk + T[idx(i-1,j,  k,  p.ny, p.nz)];
                double d2y  = T[idx(i,  j+1,k,  p.ny, p.nz)] - 2*Tijk + T[idx(i,  j-1,k,  p.ny, p.nz)];
                double d2z  = T[idx(i,  j,  k+1,p.ny, p.nz)] - 2*Tijk + T[idx(i,  j,  k-1,p.ny, p.nz)];
                T_new[idx(i,j,k,p.ny,p.nz)] = Tijk + rx*d2x + ry*d2y + rz*d2z;
            }
        }

        applyBC(T_new);
        std::swap(T, T_new);
        time += dt;
    }

    auto t1 = high_resolution_clock::now();
    const double elapsed = duration_cast<milliseconds>(t1-t0).count()/1000.0;
    std::cout << "\n  Simulation done in " << elapsed << " s\n";

    // Параметры расчёта — для подписей графиков (report_plots.py)
    std::ofstream prm(outDir + "/params.csv");
    prm << "key,value\n"
        << "nx," << p.nx << "\nny," << p.ny << "\nnz," << p.nz << "\n"
        << std::scientific << "alpha," << p.alpha << "\n" << std::defaultfloat
        << "t_end," << p.t_end << "\nt_init," << p.t_init << "\n"
        << "t_xm," << p.t_xm << "\nt_xp," << p.t_xp << "\n"
        << "t_ym," << p.t_ym << "\nt_yp," << p.t_yp << "\n"
        << "t_zm," << p.t_zm << "\nt_zp," << p.t_zp << "\n"
        << "threads," << nThreads << "\nelapsed," << elapsed << "\n";
    std::cout << "  Output saved to: ./" << outDir << "/\n";
    return 0;
}
