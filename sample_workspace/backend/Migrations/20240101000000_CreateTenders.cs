using Microsoft.EntityFrameworkCore.Migrations;

namespace SampleApi.Migrations;

public partial class CreateTenders : Migration
{
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.CreateTable(
            name: "Tenders",
            columns: table => new
            {
                Id = table.Column<int>(type: "int", nullable: false),
                Title = table.Column<string>(type: "nvarchar(256)", nullable: false),
                Description = table.Column<string>(type: "nvarchar(max)", nullable: true),
                Status = table.Column<string>(type: "nvarchar(64)", nullable: false),
                CreatedAt = table.Column<DateTime>(type: "datetime2", nullable: false),
                CreatedByUserId = table.Column<int>(type: "int", nullable: true)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_Tenders", x => x.Id);
            });

        migrationBuilder.CreateTable(
            name: "Users",
            columns: table => new
            {
                Id = table.Column<int>(type: "int", nullable: false),
                UserName = table.Column<string>(type: "nvarchar(128)", nullable: false)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_Users", x => x.Id);
            });
    }
}
