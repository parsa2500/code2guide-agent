using Microsoft.EntityFrameworkCore;
using SampleApi.Entities;

namespace SampleApi.Data;

public class AppDbContext : DbContext
{
    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }

    public DbSet<Tender> Tenders { get; set; } = null!;
    public DbSet<User> Users { get; set; } = null!;
}
